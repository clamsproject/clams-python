"""
HuggingFace transformers backend helpers.

Two general loaders that wrap the device / kwargs / inference-mode
boilerplate every HF-backed CLAMS app does identically:

* :func:`load_hf_model` -- ``from_pretrained()`` flow for any model
  class (instruction-tuned LLMs/VLMs, encoder-only classifiers,
  vision/audio feature extractors, etc.). Use when the app needs raw
  access to the underlying model and processor.
* :func:`load_hf_pipeline` -- task-level :func:`transformers.pipeline`
  flow (ASR, NER, text classification, zero-shot, etc.). Use when
  pipeline-level inference is sufficient.

``torch`` and ``transformers`` are optional dependencies. Install them
via the ``[hf]`` extra::

    pip install clams-python[hf]

Imports are lazy: this module can be referenced from
:mod:`clams.app` without triggering an ``ImportError`` on a base
``clams-python`` install. The :class:`ImportError` only fires when a
loader is actually called without the extras.
"""
from typing import Any, Optional, Tuple, Union


def load_hf_model(
        model_id: str,
        model_cls,
        processor_cls=None,
        dtype=None,
        device: Optional[str] = None,
        padding_side: Optional[str] = None,
        revision: Optional[str] = None,
        model_kwargs: Optional[dict] = None,
        processor_kwargs: Optional[dict] = None,
) -> Tuple[Any, Any, str]:
    """
    Load a HuggingFace ``transformers`` model via ``from_pretrained``
    and return it ready for inference.

    :param model_id: HuggingFace model identifier (e.g., a Hub repo
        name or a local path) forwarded to ``from_pretrained``.
    :param model_cls: a ``transformers`` model class (e.g.,
        ``AutoModelForCausalLM``, ``AutoModelForImageTextToText``,
        ``ConvNextV2Model``, ``ViTModel``, ...). Whatever supports
        ``from_pretrained()``.
    :param processor_cls: a processor / tokenizer / feature-extractor
        class with ``from_pretrained()``. Defaults to
        ``transformers.AutoProcessor``. Pass ``transformers.AutoTokenizer``,
        ``transformers.AutoImageProcessor``, etc. for narrower cases.
        Pass ``None`` explicitly to skip processor loading entirely
        (the returned ``processor`` in that case is ``None``).
    :param dtype: torch dtype for the model (e.g., ``torch.bfloat16``).
        When ``None`` (default), no ``torch_dtype`` kwarg is forwarded
        to ``from_pretrained`` -- the model class uses its own default
        (typically float32). Set explicitly for low-precision LLM
        inference.
    :param device: target device string (e.g., ``'cuda'``, ``'cpu'``,
        ``'cuda:0'``). When ``None`` (default), the helper auto-detects
        cuda availability and falls back to cpu.
    :param padding_side: if set (typically ``'left'`` for decoder-only
        models doing batched generation), the helper configures the
        underlying tokenizer's ``padding_side`` and -- when no pad
        token is set -- uses the EOS token as the pad token. Leave
        ``None`` for encoder / non-batched cases (the tokenizer's own
        default is preserved).
    :param revision: optional Git revision (commit hash, branch name,
        or tag) on the Hub repository to pin the download to. When
        set, forwarded as ``revision=...`` to both
        ``model_cls.from_pretrained`` and
        ``processor_cls.from_pretrained``, ensuring the model and
        processor are loaded from the same commit. Strongly recommended
        for production: pinning a commit hash makes the analyzer
        artifact reproducible and immune to upstream silent updates.
        Apps calling this helper directly should record the same hash
        on ``analyzer_version`` (or ``analyzer_versions``) in
        ``metadata.py`` so the output MMIF identifies the exact
        artifact. Apps inheriting from
        :class:`~clams.app.ClamsHFPromptableApp` do not call this
        helper -- the base class reads ``analyzer_versions`` from the
        app metadata and forwards the resolved revision automatically.
    :param model_kwargs: extra kwargs forwarded to
        ``model_cls.from_pretrained()`` (e.g.,
        ``{'use_safetensors': True, 'add_pooling_layer': False}``).
    :param processor_kwargs: extra kwargs forwarded to
        ``processor_cls.from_pretrained()`` (e.g.,
        ``{'use_safetensors': True, 'use_fast': True}``).

    :returns: ``(processor, model, device)`` tuple. ``processor`` is
        the loaded processor/tokenizer/feature-extractor (or ``None``
        if ``processor_cls`` was explicitly set to ``None``).
        ``device`` is the resolved device string the model was moved
        to.
    :rtype: Tuple[Any, Any, str]
    :raises ImportError: if ``torch`` or ``transformers`` is not
        installed. Install the ``[hf]`` extra to fix.
    """
    try:
        import torch  # pytype: disable=import-error
    except ImportError as e:
        raise ImportError(
            "clams.backends.hf requires the `torch` package. "
            "Install with: pip install clams-python[hf]"
        ) from e
    try:
        import transformers  # pytype: disable=import-error
    except ImportError as e:
        raise ImportError(
            "clams.backends.hf requires the `transformers` package. "
            "Install with: pip install clams-python[hf]"
        ) from e

    resolved_device = device or ('cuda' if torch.cuda.is_available() else 'cpu')

    # Processor.
    if processor_cls is None and processor_kwargs is None:
        # default to AutoProcessor
        processor_cls = transformers.AutoProcessor
    if processor_cls is not None:
        processor_load_kwargs = dict(processor_kwargs or {})
        if revision is not None:
            processor_load_kwargs.setdefault('revision', revision)
        processor = processor_cls.from_pretrained(
            model_id, **processor_load_kwargs)
        if padding_side is not None:
            tokenizer = getattr(processor, 'tokenizer', processor)
            tokenizer.padding_side = padding_side
            if getattr(tokenizer, 'pad_token', None) is None:
                eos = getattr(tokenizer, 'eos_token', None)
                if eos is not None:
                    tokenizer.pad_token = eos
    else:
        processor = None

    # Model.
    model_load_kwargs = dict(model_kwargs or {})
    if dtype is not None:
        model_load_kwargs['torch_dtype'] = dtype
    if revision is not None:
        model_load_kwargs.setdefault('revision', revision)
    model = model_cls.from_pretrained(model_id, **model_load_kwargs)
    model = model.to(resolved_device)
    model.eval()

    return processor, model, resolved_device


def load_hf_pipeline(
        task: str,
        model_id: str,
        device: Optional[Union[str, int]] = None,
        revision: Optional[str] = None,
        model_kwargs: Optional[dict] = None,
        pipeline_kwargs: Optional[dict] = None,
) -> Tuple[Any, Union[str, int]]:
    """
    Load a HuggingFace :func:`transformers.pipeline` for ``task`` and
    return it ready for inference. Wraps the device / revision /
    kwargs-forwarding boilerplate that every pipeline-backed CLAMS
    app does identically. Use this for apps wrapping a task-level
    pipeline (ASR via ``"automatic-speech-recognition"``, NER via
    ``"token-classification"``, text classification, zero-shot, etc.);
    use :func:`load_hf_model` instead when the app needs raw access
    to the underlying model / processor (e.g., for custom chat-template
    formatting or batched ``generate`` calls).

    :param task: pipeline task string forwarded to
        :func:`transformers.pipeline` (e.g.,
        ``"automatic-speech-recognition"``, ``"token-classification"``).
    :param model_id: HuggingFace model identifier (Hub repo name or
        local path) forwarded to ``pipeline(model=...)``.
    :param device: target device. Accepts the string form
        (``'cuda'``, ``'cpu'``, ``'cuda:0'``) for parity with
        :func:`load_hf_model`, or the integer form accepted natively
        by ``pipeline`` (``-1`` for CPU, ``0+`` for GPU index). When
        ``None`` (default), auto-detects cuda availability and falls
        back to cpu (string form).
    :param revision: optional Git revision (commit hash, branch, or
        tag) on the Hub to pin the download to. Strongly recommended
        for production; see :func:`load_hf_model` for rationale.
    :param model_kwargs: extra kwargs forwarded to the underlying
        ``model.from_pretrained()`` via the
        ``pipeline(model_kwargs={...})`` channel.
    :param pipeline_kwargs: extra kwargs forwarded directly to
        :func:`transformers.pipeline` (e.g. ``generate_kwargs``,
        ``tokenizer``, ``feature_extractor``, ``batch_size``,
        ``framework``). ``model``, ``task``, ``device``, ``revision``,
        and ``model_kwargs`` are owned by this helper -- explicit
        helper args take precedence if any collide.
    :returns: ``(pipeline, device)`` tuple. ``device`` is the resolved
        device the pipeline is on, in the form it was passed (or the
        auto-resolved string form when ``device=None``).
    :rtype: Tuple[Any, Union[str, int]]
    :raises ImportError: if ``torch`` or ``transformers`` is not
        installed. Install the ``[hf]`` extra to fix.
    """
    try:
        import torch  # pytype: disable=import-error
    except ImportError as e:
        raise ImportError(
            "clams.backends.hf requires the `torch` package. "
            "Install with: pip install clams-python[hf]"
        ) from e
    try:
        from transformers import pipeline  # pytype: disable=import-error
    except ImportError as e:
        raise ImportError(
            "clams.backends.hf requires the `transformers` package. "
            "Install with: pip install clams-python[hf]"
        ) from e

    resolved_device = device if device is not None else (
        'cuda' if torch.cuda.is_available() else 'cpu')

    pipeline_call_kwargs = dict(pipeline_kwargs or {})
    # Helper-owned keys: explicit args win on collision.
    for owned in ('task', 'model', 'device'):
        pipeline_call_kwargs.pop(owned, None)
    if model_kwargs:
        pipeline_call_kwargs['model_kwargs'] = dict(model_kwargs)
    if revision is not None:
        pipeline_call_kwargs['revision'] = revision

    pipe = pipeline(
        task,
        model=model_id,
        device=resolved_device,
        **pipeline_call_kwargs,
    )
    return pipe, resolved_device
