"""
llama.cpp ``llama-server`` backend helpers.

A CLAMS app that uses this backend runs its model in a private
``llama-server`` process: the app downloads a pinned GGUF file (and,
for vision models, its ``mmproj`` projector file), starts the server
on a free localhost port, talks to it through the OpenAI-compatible
chat API, and stops it when the app exits. The server is never shared
with, or borrowed from, anything outside the app; model selection stays
with the app.

* :func:`find_llama_server` -- locate the ``llama-server`` executable.
* :func:`resolve_gguf_files` -- find the GGUF file(s) and the ``mmproj``
  file of a quantization variant in a Hugging Face Hub repository.
* :func:`download_gguf` -- download those files at a pinned revision.
* :func:`check_gpu_memory` -- refuse to start when the visible GPUs
  cannot hold the weights.
* :class:`LlamaServer` -- start, health-check, query and stop one
  ``llama-server`` process.
* :func:`to_openai_messages` -- turn a conversation built by
  :py:meth:`clams.app.ClamsPromptableApp.build_conversation` into
  OpenAI chat messages, with images as base64 data URLs.

The ``llama-server`` binary itself is not a python dependency. It is
found, in this order, from the ``binary`` argument, the
``LLAMA_SERVER`` environment variable, or ``llama-server`` on the
``PATH``. ``huggingface_hub`` and ``pillow`` come with the
``[llamaserver]`` extra::

    pip install clams-python[llamaserver]
"""

import atexit
import base64
import collections
import io
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Deque, List, Optional, Sequence, Tuple

__all__ = ['LLAMA_SERVER_ENV', 'LlamaServer', 'check_gpu_memory',
           'download_gguf', 'find_llama_server', 'resolve_gguf_files',
           'to_openai_messages']

#: environment variable naming the ``llama-server`` binary to run
LLAMA_SERVER_ENV = 'LLAMA_SERVER'

_SHARD_PATTERN = re.compile(r'-(\d{5})-of-(\d{5})\.gguf$')
_LOG_TAIL_LINES = 40


def find_llama_server(binary: Optional[str] = None) -> str:
    """
    Locate the ``llama-server`` executable.

    :param binary: explicit path or command name. When ``None``, the
        ``LLAMA_SERVER`` environment variable is used, then
        ``llama-server`` on the ``PATH``.
    :return: absolute path of the executable.
    :raises FileNotFoundError: if no executable is found.
    """
    candidate = binary or os.environ.get(LLAMA_SERVER_ENV) or 'llama-server'
    resolved = shutil.which(candidate)
    if resolved is None:
        raise FileNotFoundError(
            f"llama-server executable not found (looked for "
            f"{candidate!r}). Install llama.cpp, put llama-server on the "
            f"PATH, or set the {LLAMA_SERVER_ENV} environment variable "
            f"to its path.")
    return resolved


def _free_port(host: str = '127.0.0.1') -> int:
    """Return a TCP port on ``host`` that is free at the time of the call."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def _pick_gguf_files(
        filenames: Sequence[str],
        variant: str = '',
) -> Tuple[List[str], Optional[str]]:
    """
    Choose the model file(s) and the ``mmproj`` file of one
    quantization variant from a repository file listing.

    Files whose base name starts with ``mmproj`` are projector files;
    every other ``.gguf`` file is a model file. A model file matches
    ``variant`` when the variant string occurs in its name, ignoring
    case. A model split into shards (``*-00001-of-00003.gguf``) is
    returned as all of its shards, in order; llama.cpp loads the rest
    from the first.

    :param filenames: repository file names (paths relative to the
        repository root).
    :param variant: quantization tag such as ``Q8_0`` or ``Q4_K_M``.
        Empty means the repository holds exactly one model.
    :return: ``(model_files, mmproj_file)``; ``mmproj_file`` is
        ``None`` when the repository has no projector.
    :raises ValueError: if no model file, several model files, or
        several projector files match.
    """
    ggufs = sorted(f for f in filenames if f.lower().endswith('.gguf'))
    projectors = [f for f in ggufs
                  if os.path.basename(f).lower().startswith('mmproj')]
    models = [f for f in ggufs if f not in projectors]
    if variant:
        models = [f for f in models if variant.lower() in f.lower()]
    if not models:
        raise ValueError(
            f"no GGUF model file matches variant {variant!r}; "
            f"available: {[f for f in ggufs if f not in projectors]}")
    if len(models) > 1:
        shards = [_SHARD_PATTERN.search(f) for f in models]
        totals = {m.group(2) for m in shards if m}
        if not (all(shards) and len(totals) == 1
                and len(models) == int(totals.pop())):
            raise ValueError(
                f"variant {variant!r} matches several GGUF files: "
                f"{models}; name the file explicitly in MODEL_FILES")
    if len(projectors) > 1:
        raise ValueError(
            f"repository has several mmproj files: {projectors}; name "
            f"the one to use explicitly in MODEL_FILES")
    return models, (projectors[0] if projectors else None)


def resolve_gguf_files(
        repo_id: str, revision: str, variant: str = '',
) -> Tuple[List[str], Optional[str]]:
    """
    List a Hugging Face Hub repository at ``revision`` and pick the
    files of ``variant`` with :func:`_pick_gguf_files`.
    """
    try:
        from huggingface_hub import HfApi
    except ImportError as e:
        raise ImportError(
            "The llama-server backend requires huggingface_hub. Install "
            "it via `pip install clams-python[llamaserver]`.") from e
    files = HfApi().list_repo_files(repo_id, revision=revision)
    return _pick_gguf_files(files, variant)


def download_gguf(
        repo_id: str,
        revision: str,
        model_files: Sequence[str],
        mmproj_file: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    """
    Download pinned GGUF files from the Hugging Face Hub (or reuse the
    local cache) and return their local paths.

    :param repo_id: Hub repository, e.g. ``ggml-org/gemma-3-4b-it-GGUF``.
    :param revision: commit hash the files are pinned to.
    :param model_files: model file name(s); several for a sharded model.
    :param mmproj_file: projector file name, or ``None``.
    :return: ``(model_paths, mmproj_path)``.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        raise ImportError(
            "The llama-server backend requires huggingface_hub. Install "
            "it via `pip install clams-python[llamaserver]`.") from e
    model_paths = [hf_hub_download(repo_id, f, revision=revision)
                   for f in model_files]
    mmproj_path = (hf_hub_download(repo_id, mmproj_file, revision=revision)
                   if mmproj_file else None)
    return model_paths, mmproj_path


def _gpu_free_memory_mb() -> Optional[List[int]]:
    """
    Free memory of each visible NVIDIA GPU in MiB, from ``nvidia-smi``.
    Honors ``CUDA_VISIBLE_DEVICES`` when it holds GPU indices.

    :return: one value per visible GPU, or ``None`` when ``nvidia-smi``
        is unavailable or fails (no NVIDIA GPU, or no driver).
    """
    if shutil.which('nvidia-smi') is None:
        return None
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=index,memory.free',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    free = {}
    for line in result.stdout.strip().splitlines():
        index, mem = (part.strip() for part in line.split(','))
        free[index] = int(float(mem))
    visible = os.environ.get('CUDA_VISIBLE_DEVICES')
    if visible is not None:
        wanted = [v.strip() for v in visible.split(',') if v.strip()]
        if all(v.isdigit() for v in wanted):
            return [free[v] for v in wanted if v in free]
    return list(free.values())


def check_gpu_memory(required_mb: int,
                     free_mb: Optional[List[int]] = None) -> None:
    """
    Raise when the visible GPUs together have less free memory than
    ``required_mb``. Does nothing when no GPU is visible (the server
    then runs on CPU).

    llama.cpp splits a model across GPUs layer by layer, so the free
    memory of all visible GPUs counts. Memory held by other processes
    (for example a model kept loaded by another service) is not free.

    :param required_mb: lower bound of the memory the model needs,
        typically the size of its files.
    :param free_mb: free memory per GPU; read with
        :func:`_gpu_free_memory_mb` when ``None``.
    :raises RuntimeError: if the free memory is insufficient.
    """
    if free_mb is None:
        free_mb = _gpu_free_memory_mb()
    if not free_mb:
        return
    if sum(free_mb) < required_mb:
        raise RuntimeError(
            f"the model needs at least {required_mb} MiB of GPU memory, "
            f"but the visible GPUs have {free_mb} MiB free. Free GPU "
            f"memory (other processes may hold loaded models) or choose "
            f"a smaller model.")


def _image_to_data_url(image: Any) -> str:
    """
    Encode an image as a ``data:image/png;base64,...`` URL.

    :param image: a PIL image, a numpy array (as returned by
        ``mmif.utils.video_document_helper``), a path to an image
        file, or a string that already is an ``http(s)://`` or
        ``data:`` URL (returned unchanged).
    """
    if isinstance(image, str):
        if image.startswith(('http://', 'https://', 'data:')):
            return image
        with open(image, 'rb') as f:
            raw = f.read()
        return 'data:image/png;base64,' + base64.b64encode(raw).decode()
    from PIL import Image
    if not isinstance(image, Image.Image):
        image = Image.fromarray(image)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(
        buffer.getvalue()).decode()


def to_openai_messages(conversation: List[dict]) -> List[dict]:
    """
    Convert a conversation in the SDK's chat format (see
    :py:meth:`clams.app.ClamsPromptableApp.build_conversation`) into
    OpenAI chat messages. Text parts pass through; image parts become
    ``image_url`` parts with base64 data URLs.

    :raises ValueError: for audio parts, which this backend does not
        support yet.
    """
    messages = []
    for message in conversation:
        content = message.get('content')
        if isinstance(content, list):
            parts = []
            for part in content:
                kind = part.get('type')
                if kind == 'text':
                    parts.append({'type': 'text', 'text': part['text']})
                elif kind == 'image':
                    parts.append({
                        'type': 'image_url',
                        'image_url': {'url': _image_to_data_url(
                            part['image'])}})
                else:
                    raise ValueError(
                        f"content part type {kind!r} is not supported by "
                        f"the llama-server backend")
            content = parts
        messages.append({'role': message['role'], 'content': content})
    return messages


class LlamaServer:
    """
    One ``llama-server`` process serving one model on localhost.

    The process belongs to the python process that started it: only
    that process stops it, so a forked child (e.g. a gunicorn worker)
    exiting does not take the server down with it. The server is also
    stopped at interpreter exit.

    :param model_path: local path of the GGUF model file (the first
        shard for a sharded model).
    :param mmproj_path: local path of the projector file for vision
        input, or ``None``.
    :param binary: ``llama-server`` executable; see
        :func:`find_llama_server`.
    :param host: interface to bind; keep the default so the server is
        reachable only from this machine.
    :param port: port to bind; a free port is chosen when ``None``.
    :param n_gpu_layers: layers to offload to GPUs. ``None`` offloads
        all layers when an NVIDIA GPU is visible and none otherwise,
        so a model that does not fit fails to load instead of running
        partly on CPU.
    :param ctx_size: total context size in tokens, shared by the
        parallel slots.
    :param n_parallel: number of parallel slots (requests the server
        decodes together).
    :param extra_args: further ``llama-server`` command-line arguments.
    :param startup_timeout: seconds to wait for the model to load.
    :param logger: logger receiving the server's output at DEBUG level.
    """

    def __init__(
            self,
            model_path: str,
            mmproj_path: Optional[str] = None,
            *,
            binary: Optional[str] = None,
            host: str = '127.0.0.1',
            port: Optional[int] = None,
            n_gpu_layers: Optional[int] = None,
            ctx_size: int = 8192,
            n_parallel: int = 1,
            extra_args: Sequence[str] = (),
            startup_timeout: float = 600.0,
            logger: Optional[logging.Logger] = None,
    ):
        self.model_path = model_path
        self.mmproj_path = mmproj_path
        self.binary = binary
        self.host = host
        self.port = port
        self.n_gpu_layers = n_gpu_layers
        self.ctx_size = ctx_size
        self.n_parallel = n_parallel
        self.extra_args = list(extra_args)
        self.startup_timeout = startup_timeout
        self.logger = logger or logging.getLogger(__name__)
        self._process: Optional[subprocess.Popen] = None
        self._owner_pid: Optional[int] = None
        self._log_tail: Deque[str] = collections.deque(
            maxlen=_LOG_TAIL_LINES)

    @property
    def base_url(self) -> str:
        """``http://host:port`` of the running server."""
        return f"http://{self.host}:{self.port}"

    def _command(self) -> List[str]:
        """The command line used to start the server."""
        n_gpu_layers = self.n_gpu_layers
        if n_gpu_layers is None:
            n_gpu_layers = 999 if _gpu_free_memory_mb() else 0
        cmd = [find_llama_server(self.binary),
               '--model', self.model_path,
               '--host', self.host, '--port', str(self.port),
               '--ctx-size', str(self.ctx_size),
               '--parallel', str(self.n_parallel),
               '--n-gpu-layers', str(n_gpu_layers),
               # chat template from the GGUF metadata
               '--jinja',
               # keep reasoning ("thinking") tags in the text, as the HF
               # backend does, so apps split them with
               # ``split_tagged_reasoning_trace``
               '--reasoning-format', 'none']
        if self.mmproj_path:
            cmd += ['--mmproj', self.mmproj_path]
        return cmd + self.extra_args

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> 'LlamaServer':
        """
        Start the server and block until it reports healthy.

        :raises RuntimeError: if the process exits or does not become
            healthy within ``startup_timeout``; the message includes the
            last lines of the server's output.
        """
        if self.is_running():
            return self
        if self.port is None:
            self.port = _free_port(self.host)
        cmd = self._command()
        self.logger.info(f"Starting llama-server: {' '.join(cmd)}")
        self._log_tail.clear()
        self._process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, bufsize=1)
        self._owner_pid = os.getpid()
        threading.Thread(target=self._forward_output, daemon=True).start()
        atexit.register(self.stop)
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                time.sleep(0.2)  # let the reader thread drain the pipe
                raise RuntimeError(
                    f"llama-server exited with code "
                    f"{self._process.returncode} during startup:\n"
                    + '\n'.join(self._log_tail))
            if self._healthy():
                self.logger.info(f"llama-server ready at {self.base_url}")
                return self
            time.sleep(0.5)
        self.stop()
        raise RuntimeError(
            f"llama-server did not become healthy within "
            f"{self.startup_timeout} s:\n" + '\n'.join(self._log_tail))

    def stop(self) -> None:
        """Stop the server if this process started it."""
        process = self._process
        if process is None or os.getpid() != self._owner_pid:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self._process = None

    def __enter__(self) -> 'LlamaServer':
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def chat(self, messages: List[dict], **params) -> str:
        """
        Send one chat completion request and return the reply text.

        :param messages: OpenAI chat messages (see
            :func:`to_openai_messages`).
        :param params: further request fields, e.g. ``max_tokens``,
            ``temperature``, ``top_p``, ``top_k``,
            ``chat_template_kwargs``.
        """
        body = json.dumps({'messages': messages, **params}).encode()
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions", data=body,
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request) as response:
                reply = json.load(response)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors='replace')
            raise RuntimeError(
                f"llama-server returned HTTP {e.code}: {detail}") from e
        return reply['choices'][0]['message'].get('content') or ''

    def _healthy(self) -> bool:
        try:
            with urllib.request.urlopen(
                    f"{self.base_url}/health", timeout=2) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def _forward_output(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            line = line.rstrip()
            self._log_tail.append(line)
            self.logger.debug(f"[llama-server] {line}")
