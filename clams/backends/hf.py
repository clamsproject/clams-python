"""
HuggingFace transformers backend helper.

Provides :func:`load_hf_model`, a general loader that wraps the device,
processor, dtype, and inference-mode boilerplate every HF-backed CLAMS
app does identically. Usable for any model class that supports
``from_pretrained()``: instruction-tuned LLMs/VLMs, encoder-only
classifiers, vision/audio feature extractors, etc.

``torch`` and ``transformers`` are optional dependencies. Install them
via the ``[hf]`` extra::

    pip install clams-python[hf]

Imports are lazy: this module can be referenced from
:mod:`clams.app` without triggering an ``ImportError`` on a base
``clams-python`` install. The :class:`ImportError` only fires when
:func:`load_hf_model` is actually called without the extras.
"""
from typing import Any, Optional, Tuple


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
