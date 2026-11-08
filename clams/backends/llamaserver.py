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

Server settings other than the model files and the address are
llama.cpp's own ``LLAMA_ARG_*`` environment variables, which
``llama-server`` reads for every argument not given on its command
line. Their values come from, in increasing precedence:

1. ``llama-server``'s defaults, which fit the run to the hardware:
   they place what fits on the GPUs, keep the rest in system memory,
   and size the context to the free memory;
1. the ``llama_args`` of :class:`LlamaServer`, for what a model needs
   (e.g. ``{'LLAMA_ARG_UBATCH': '2048'}``);
1. the environment of the process that starts the server (e.g.
   ``LLAMA_ARG_CTX_SIZE``, ``LLAMA_ARG_THREADS``,
   ``LLAMA_ARG_N_GPU_LAYERS`` set by whoever runs the app).
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
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Deque, List, Mapping, Optional, Sequence, Tuple

__all__ = ['LLAMA_SERVER_ENV', 'ContextSizeError', 'LlamaServer',
           'download_gguf', 'find_llama_server', 'resolve_gguf_files',
           'to_openai_messages']

#: environment variable naming the ``llama-server`` binary to run
LLAMA_SERVER_ENV = 'LLAMA_SERVER'

_SHARD_PATTERN = re.compile(r'-(\d{5})-of-(\d{5})\.gguf$')
_DRAFT_PREFIXES = ('mtp-', 'dflash-', 'draft-')
_LOG_TAIL_LINES = 40
_LLAMA_ARG_PREFIX = 'LLAMA_ARG_'
# the server's address is always given on the command line, so these two
# are dropped from its environment (the upstream image sets them)
_ADDRESS_ENV = ('LLAMA_ARG_HOST', 'LLAMA_ARG_PORT')
# server log lines: optional timestamp, then a level letter
_LEVEL_LINE = re.compile(r'^(?:[\d.]+\s+)?[ew]\s')


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

    Files whose base name starts with ``mmproj`` are projector files.
    Files with a speculative-decoding prefix (``mtp-``, ``dflash-``,
    ``draft-``) are draft models and are skipped. Every other
    ``.gguf`` file is a model file. A model file matches ``variant``
    when the variant string occurs in its name, ignoring case. When a
    repository has several projectors, the one matching ``variant``
    is chosen if exactly one does. A model split into shards
    (``*-00001-of-00003.gguf``) is returned as all of its shards, in
    order; llama.cpp loads the rest from the first.

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
    models = [f for f in ggufs if f not in projectors
              and not os.path.basename(f).lower().startswith(_DRAFT_PREFIXES)]
    if variant:
        models = [f for f in models if variant.lower() in f.lower()]
        matching = [f for f in projectors if variant.lower() in f.lower()]
        if len(matching) == 1:
            projectors = matching
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
    files of ``variant`` with :func:`_pick_gguf_files`. When the Hub
    cannot be reached (offline mode, or no network), the files of the
    revision already in the local cache are listed instead, so a
    cached model starts without network.
    """
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError as e:
        raise ImportError(
            "The llama-server backend requires huggingface_hub. Install "
            "it via `pip install clams-python[llamaserver]`.") from e
    try:
        files = HfApi().list_repo_files(repo_id, revision=revision)
    except Exception as online_error:
        try:
            snapshot = snapshot_download(
                repo_id, revision=revision, local_files_only=True)
        except Exception:
            raise online_error
        files = [os.path.relpath(os.path.join(root, name), snapshot)
                 for root, _, names in os.walk(snapshot) for name in names]
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


def _log_level(line: str) -> int:
    """Logging level for one line of ``llama-server`` output."""
    lowered = line.lower()
    if re.search(r'\b(error|failed|warning|warn)\b', lowered) \
            or _LEVEL_LINE.match(lowered):
        return logging.WARNING
    # device placement, load, readiness and timing lines
    if 'print_timing' in lowered or 'model loaded' in lowered \
            or 'server is listening' in lowered or 'offloaded' in lowered:
        return logging.INFO
    return logging.DEBUG


class ContextSizeError(RuntimeError):
    """A request was longer than the context of the server's slot."""


def _exit_on_sigterm() -> None:
    """
    Turn a SIGTERM with the default action into ``SystemExit``, so that
    ``atexit`` handlers (and with them :py:meth:`LlamaServer.stop`) run
    when the app is stopped with ``kill`` or ``docker stop``. Leaves a
    SIGTERM handler that someone else installed (e.g. gunicorn's) alone,
    and does nothing outside the main thread, where python cannot set
    signal handlers.
    """
    if threading.current_thread() is not threading.main_thread():
        return
    if signal.getsignal(signal.SIGTERM) is signal.SIG_DFL:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(128 + 15))


class LlamaServer:
    """
    One ``llama-server`` process serving one model on localhost.

    The process belongs to the python process that started it: only
    that process stops it, so a forked child (e.g. a gunicorn worker)
    exiting does not take the server down with it. The server is also
    stopped at interpreter exit, including a SIGTERM to the main
    process. A SIGKILL (or an out-of-memory kill) of the python process
    leaves the server running.

    :param model_path: local path of the GGUF model file (the first
        shard for a sharded model).
    :param mmproj_path: local path of the projector file for vision
        input, or ``None``.
    :param binary: ``llama-server`` executable; see
        :func:`find_llama_server`.
    :param host: interface to bind; keep the default so the server is
        reachable only from this machine.
    :param port: port to bind; a free port is chosen when ``None``.
    :param llama_args: default values of ``LLAMA_ARG_*`` environment
        variables for the server, e.g. ``{'LLAMA_ARG_UBATCH': '2048'}``.
        A variable set in the environment of this process takes
        precedence (see the module docstring). The context size and slot
        count the server ends up with are read after startup into
        :py:attr:`slot_context` and :py:attr:`slots`.
    :param startup_timeout: seconds to wait for the model to load. A
        large model on a slow disk needs more than the default (the
        server reads the whole file at startup).
    :param request_timeout: seconds to wait for one chat completion.
    :param logger: logger receiving the server's output: errors and
        warnings at WARNING, placement, load and timing lines at INFO,
        the rest at DEBUG.
    :raises ValueError: if a ``llama_args`` key is not an
        ``LLAMA_ARG_*`` variable, or names the server's address.
    """

    def __init__(
            self,
            model_path: str,
            mmproj_path: Optional[str] = None,
            *,
            binary: Optional[str] = None,
            host: str = '127.0.0.1',
            port: Optional[int] = None,
            llama_args: Optional[Mapping[str, Any]] = None,
            startup_timeout: float = 600.0,
            request_timeout: float = 1800.0,
            logger: Optional[logging.Logger] = None,
    ):
        llama_args = dict(llama_args or {})
        invalid = [k for k in llama_args
                   if not k.startswith(_LLAMA_ARG_PREFIX)
                   or k in _ADDRESS_ENV]
        if invalid:
            raise ValueError(
                f"llama_args takes {_LLAMA_ARG_PREFIX}* environment "
                f"variables other than {', '.join(_ADDRESS_ENV)}: "
                f"{invalid}")
        self.model_path = model_path
        self.mmproj_path = mmproj_path
        self.binary = binary
        self.host = host
        self.port = port
        self.llama_args = {k: str(v) for k, v in llama_args.items()}
        self.startup_timeout = startup_timeout
        self.request_timeout = request_timeout
        self.logger = logger or logging.getLogger(__name__)
        #: context size of one slot in tokens, as the running server
        #: reports it (``None`` until started, or if it cannot tell)
        self.slot_context: Optional[int] = None
        #: number of requests the running server decodes together
        #: (``1`` until started, or if it cannot tell)
        self.slots: int = 1
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
        cmd = [find_llama_server(self.binary),
               '--model', self.model_path,
               '--host', self.host, '--port', str(self.port),
               # keep reasoning ("thinking") tags in the text, as the HF
               # backend does, so apps split them with
               # ``split_tagged_reasoning_trace``
               '--reasoning-format', 'none']
        if self.mmproj_path:
            cmd += ['--mmproj', self.mmproj_path]
        return cmd

    def _environment(self) -> Tuple[dict, List[str]]:
        """
        The server's environment: this process's, over the defaults in
        :py:attr:`llama_args`, without the address variables. Also
        returns the ``LLAMA_ARG_*`` settings in effect with their
        source, for the log.
        """
        env = {**self.llama_args, **os.environ}
        for key in _ADDRESS_ENV:
            env.pop(key, None)
        settings = [
            f"{k}={env[k]} "
            f"({'environment' if k in os.environ else 'app'})"
            for k in sorted(env) if k.startswith(_LLAMA_ARG_PREFIX)]
        return env, settings

    def owned_here(self) -> bool:
        """Whether this python process started (and may stop) the server."""
        return self._process is not None and os.getpid() == self._owner_pid

    def is_running(self) -> bool:
        """
        Whether the server process is alive. A forked child (e.g. a
        gunicorn worker of an app whose server started before the
        fork) cannot wait on its parent's child process, so it asks the
        server's ``/health`` endpoint instead.
        """
        if self._process is None:
            return False
        if not self.owned_here():
            return self._healthy()
        return self._process.poll() is None

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
        env, settings = self._environment()
        self.logger.info(f"Starting llama-server: {' '.join(cmd)}"
                         + (f"; {', '.join(settings)}" if settings
                            else ''))
        self._log_tail.clear()
        self._process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, encoding='utf-8',
            errors='replace', bufsize=1, env=env)
        self._owner_pid = os.getpid()
        threading.Thread(target=self._forward_output, daemon=True).start()
        atexit.register(self.stop)
        _exit_on_sigterm()
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                time.sleep(0.2)  # let the reader thread drain the pipe
                raise RuntimeError(
                    f"llama-server exited with code "
                    f"{self._process.returncode} during startup:\n"
                    + '\n'.join(self._log_tail))
            if self._healthy():
                self.slot_context, self.slots = self._read_props()
                self.logger.info(
                    f"llama-server ready at {self.base_url}; "
                    f"{self.slots} slot(s) of "
                    f"{self.slot_context or 'unknown'} tokens")
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
        atexit.unregister(self.stop)

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
        :raises ContextSizeError: if the request does not fit in the
            context of a server slot.
        :raises RuntimeError: for any other error response.
        """
        body = json.dumps({'messages': messages, **params}).encode()
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions", data=body,
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(
                    request, timeout=self.request_timeout) as response:
                reply = json.load(response)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors='replace')
            if 'exceed_context_size' in detail:
                raise ContextSizeError(
                    f"the prompt does not fit in the context of a "
                    f"llama-server slot ({self.slot_context or 'unknown'}"
                    f" tokens): {detail}") from e
            raise RuntimeError(
                f"llama-server returned HTTP {e.code}: {detail}") from e
        return reply['choices'][0]['message'].get('content') or ''

    def _read_props(self) -> Tuple[Optional[int], int]:
        """Context size of one slot and the slot count, from ``/props``."""
        try:
            with urllib.request.urlopen(
                    f"{self.base_url}/props", timeout=5) as response:
                props = json.load(response)
        except (urllib.error.URLError, OSError, ValueError):
            return None, 1
        try:
            ctx = int(props['default_generation_settings']['n_ctx'])
        except (KeyError, TypeError, ValueError):
            ctx = None
        try:
            slots = max(1, int(props['total_slots']))
        except (KeyError, TypeError, ValueError):
            slots = 1
        return ctx, slots

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
            self.logger.log(_log_level(line), f"[llama-server] {line}")
