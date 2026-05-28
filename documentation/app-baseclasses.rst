.. _app-baseclasses:

Specialized App Base Classes
============================

Beyond the bare-minimum :class:`~clams.app.ClamsApp` introduced in
:ref:`introduction`, the SDK provides specialized base classes that capture
common structural patterns for CLAMS apps. Each specialized base class
extends :class:`~clams.app.ClamsApp` with a standardized runtime parameter
surface and helper methods appropriate to its category of app. App
developers inherit from the specialized base class that best matches what
their app does, instead of inheriting from :class:`~clams.app.ClamsApp`
directly.

This page first recaps what every CLAMS app inherits from
:class:`~clams.app.ClamsApp` (the baseline), then documents each
specialized base class and what it adds on top.

.. _app-baseline:

What every CLAMS app inherits
-----------------------------

Every CLAMS app subclasses :class:`~clams.app.ClamsApp` (directly or via
a specialized base class such as :class:`~clams.app.ClamsPromptableApp`)
and inherits its baseline behaviors: parameter casting and refinement,
view signing, JSON envelope unwrapping, CUDA memory profiling and
cleanup, error views, and a set of *universal* runtime parameters that
the SDK auto-injects into every app's metadata.

Universal parameters
^^^^^^^^^^^^^^^^^^^^

Added automatically by :meth:`~clams.app.ClamsApp.__init__` at runtime
and by the standard ``metadata.py`` template's ``__main__`` block at
``python metadata.py`` time. App developers do not declare them.

.. list-table::
   :header-rows: 1
   :widths: 18 12 18 8 44

   * - Name
     - Type
     - Default
     - Multi-valued
     - Notes
   * - ``pretty``
     - boolean
     - ``false``
     - no
     - When ``true``, the response MMIF JSON is re-formatted with
       2-space indentation.
   * - ``runningTime``
     - boolean
     - ``true``
     - no
     - When ``true``, the running time of the request is recorded in
       the view metadata.
   * - ``hwFetch``
     - boolean
     - ``false``
     - no
     - When ``true``, host hardware info (architecture, GPU and vRAM)
       is recorded in the view metadata.
   * - ``tfSamplingMode``
     - string
     - ``'representatives'``
     - no
     - For apps that process ``TimeFrame`` annotations: how to sample
       frames within each TimeFrame. Choices: ``'representatives'``,
       ``'single'``, ``'all'``. No effect on apps that do not process
       TimeFrames.

.. _sdk-managed-reserved:

SDK-managed parameter names are reserved
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Parameter names added by the SDK (the universal parameters listed
above, plus any parameters added by a specialized base class) are
reserved. An app's ``appmetadata()`` MUST NOT declare any of these
names via :meth:`AppMetadata.add_parameter` directly; doing so trips
the existing duplicate-name ``ValueError`` when the SDK tries to add
its own spec.

This reservation guarantees a uniform, predictable parameter interface
across all CLAMS apps. App developers can still customize a reserved
parameter's *default value* (but not its ``type``, ``multivalued``, or
``choices``) by mutating the ``default`` field on the already-injected
parameter object; see :ref:`promptable-customizing-defaults` for a
worked example.

.. _promptable:

Promptable CLAMS Apps
---------------------

A **promptable app** is a CLAMS app that wraps a promptable model: a large
language model (LLM), vision-language model (VLM), audio-language model
(ALM), large multimodal model (LMM), or remote generative API. The SDK
provides :class:`~clams.app.ClamsPromptableApp` as a specialized base class
for these apps. It standardizes the runtime parameter surface (prompts,
generation hyperparameters, batch size) and provides helpers for building
chat conversations and persisting model responses into MMIF.

This section is the developer guide for writing or migrating a CLAMS app
that inherits from :class:`~clams.app.ClamsPromptableApp`. For the general
CLAMS app development pattern, see the :ref:`introduction`,
:ref:`tutorial`, and :ref:`runtime-params` pages.

When to use ``ClamsPromptableApp``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Choose :class:`~clams.app.ClamsPromptableApp` over :class:`~clams.app.ClamsApp`
when your app's core operation is "given a prompt and some input
(image/audio/text/structured data), return generated text." Concretely:

- Image captioning, VLM-based OCR, scene description
- Audio captioning, transcription via ALMs
- Summarization, classification, structured-data extraction via LLMs
- Tasks driven by an LMM that takes mixed-modality inputs
- Any app that wraps a remote LLM, VLM, ALM, or LMM API and forwards a prompt

If your app does not call a generative model (e.g. a classical OCR engine,
a speech-to-text engine that doesn't take prompts, a classifier wrapping a
discriminative model), keep using :class:`~clams.app.ClamsApp` directly.

.. note::

   ``ClamsPromptableApp`` assumes an **instruction-tuned or chat-tuned**
   model: one that has been fine-tuned to follow natural-language
   instructions and that understands a system/user/assistant role
   structure. The parameter
   surface (``systemPrompt``, ``promptMode``'s turn-taking semantics, the
   chat-template message list produced by ``build_conversation``) presupposes
   this. Bare completion / next-token-prediction base models that have not
   been instruction-tuned do not fit this base class cleanly; for those, use
   :class:`~clams.app.ClamsApp` directly and design your own parameter surface.

Standardized runtime parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Every :class:`~clams.app.ClamsPromptableApp` exposes the following
SDK-managed runtime parameters in addition to the universal parameters
from :class:`~clams.app.ClamsApp`. These names are reserved; see
:ref:`sdk-managed-reserved`.

.. list-table::
   :header-rows: 1
   :widths: 18 12 18 8 44

   * - Name
     - Type
     - Default
     - Multi-valued
     - Notes
   * - ``prompt``
     - string
     - *(required, no default)*
     - yes
     - User prompt(s) sent to the model. A single value runs as a one-shot
       generation. A multi-value list is interpreted as a multi-turn static
       prompt; see :ref:`promptable-multiturn`.
   * - ``systemPrompt``
     - string
     - ``''``
     - no
     - Optional system-role text prepended to the conversation.
   * - ``promptMode``
     - string
     - ``'turn-taking'``
     - no
     - How to interpret a multi-value ``prompt`` list. Choices:
       ``'turn-taking'`` or ``'user-only'``. See :ref:`promptable-multiturn`.
   * - ``maxNewTokens``
     - integer
     - ``512``
     - no
     - Maximum number of new tokens generated per inference call. Larger values
       grow the KV cache linearly and add to GPU memory usage; reduce if VRAM
       is constrained.
   * - ``temperature``
     - number
     - ``0.0``
     - no
     - Sampling temperature. ``0.0`` selects deterministic / greedy decoding
       for maximum reproducibility; override for sampled generation.
   * - ``topP``
     - number
     - ``1.0``
     - no
     - Nucleus-sampling cumulative probability cutoff. Only meaningful when
       ``temperature`` > 0.
   * - ``topK``
     - integer
     - ``50``
     - no
     - Top-K sampling cutoff. Only meaningful when ``temperature`` > 0.
   * - ``parallelPrompts``
     - integer
     - ``1``
     - no
     - Number of independent prompts the app runs in parallel (stacks
       into a single forward pass). The *size* of each prompt (how many
       images, how long the system/user text is, etc.) is NOT regulated
       by this parameter; that is each app's responsibility. Prompt
       count and per-prompt content size combine multiplicatively for
       GPU memory, so the two can blow up together. Catastrophic
       example: ``tfSamplingMode=all`` on a TimeFrame without
       ``targets`` expands that TF into one image per native-FPS frame
       (300 images for a 10-second TF at 30fps); ``parallelPrompts=4``
       then runs 4 such prompts in one forward pass (~1200 images),
       guaranteed OOM. Keep at ``1`` on memory-tight setups; raise only
       when per-prompt content is small and bounded.

.. _promptable-customizing-defaults:

Customizing default values
""""""""""""""""""""""""""

The SDK ships sensible defaults for most promptable parameters but
deliberately leaves ``prompt`` **without** a default; prompts are
inherently app-specific and no single value is right for all apps.
Beyond ``prompt``, other defaults may also be inappropriate for a given
app: a model that needs longer outputs wants a higher ``maxNewTokens``,
a small-VRAM deployment wants ``parallelPrompts`` pinned at ``1``, etc.

Because the reservation rule prevents calling
``metadata.add_parameter('prompt', ...)`` (or any other promptable name)
directly, the recommended pattern for customizing defaults is to mutate
the ``default`` field on the already-injected parameter object right
after calling :meth:`~clams.app.ClamsPromptableApp.inject_promptable_parameters`.
You'll see a worked example of this in the ``metadata.py`` generated
by the ``clams develop`` scaffold.

This works for any promptable parameter. The parameter spec itself
(``type``, ``multivalued``, ``choices``) stays locked by the SDK; only
the ``default`` field is meant to be mutated this way, which preserves
the cross-app uniformity that the reservation rule is designed to
guarantee.

If an app *wants* to require callers to pass a value explicitly (for
``prompt`` or any other parameter), it can simply leave the default
unchanged. ``prompt`` already has no default, so the SDK will raise a
"required parameter" error if the caller omits it; for other params,
deleting the SDK default and leaving it ``None`` would have the same
effect, though that's rarely useful.

.. _promptable-declaration:

Declaring a promptable app
^^^^^^^^^^^^^^^^^^^^^^^^^^

A promptable app requires two paired edits relative to the scaffold generated
by ``clams develop``:

1. In ``app.py``, change the app class's base from :class:`~clams.app.ClamsApp`
   to :class:`~clams.app.ClamsPromptableApp` and implement
   :meth:`~clams.app.ClamsPromptableApp.generate`. The scaffold file already
   contains a guiding comment at the class declaration line.
2. In ``metadata.py``, call
   :meth:`~clams.app.ClamsPromptableApp.inject_promptable_parameters` at the
   end of ``appmetadata()``. The scaffold file already contains a
   commented-out helper-call block; uncomment it.

The ``__main__`` block in ``metadata.py`` does NOT change; it stays identical
to non-promptable apps.

The helper call inside ``appmetadata()`` makes the promptable parameters
visible to both ``python metadata.py`` (build-time discovery) and to
:meth:`~clams.app.ClamsApp._load_appmetadata` (runtime). The base class
change ensures the app inherits the parameter-presence validation, the
abstract ``generate()`` contract, and the helper methods at runtime.

The ``generate()`` contract
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Subclasses MUST implement :meth:`~clams.app.ClamsPromptableApp.generate`.
See the method's docstring for the full signature and parameter semantics.

The return value is a flat ``List[str]`` with one entry per prompt in the
batch: the outer length of ``images`` (and/or ``audios``) determines N;
``generate()`` returns ``N`` strings. For text-only single-shot calls
(both ``images`` and ``audios`` ``None``), the return is a singleton list.
Keep inference logic inside ``generate()`` distinct from MMIF I/O; the latter
belongs in ``_annotate()`` (which calls ``self.generate()``).

This separation is intentional: future SDK releases may provide default
implementations of ``generate()`` for common backends, at which point apps
that kept inference and annotation creation separate will need no changes.

.. _promptable-multiturn:

Multi-turn handling (``promptMode``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``prompt`` is always a ``List[str]`` after parameter casting. When the
list has a single element, ``promptMode`` is irrelevant (single-shot
generation). When the list has multiple elements, ``promptMode`` selects
between two multi-element prompting strategies:

**Turn-taking** (default). The list is interpreted as an alternating
user/assistant conversation: even indices (0, 2, 4, ...) are user turns,
odd indices are assistant turns. The full conversation is sent to the
model in a single ``generate`` call. This mode supports any pattern
that fits an alternating role structure, including few-shot in-context
learning (where the (user, assistant) pairs are task exemplars and the
final user turn is the new query), multi-turn dialogue continuation,
and role-play scaffolding. Example (few-shot ICL): ``["Classify
sentiment: 'I love this.'", "positive", "Classify sentiment: 'I hate
this.'", "negative", "Classify sentiment: 'It's okay.'"]``: two
exemplar pairs followed by a final query; one inference returns the
final reply.

**User-only**. Every element is a user turn; the model generates an
assistant reply between each, in N successive ``generate`` calls. Only
the final assistant response is returned per input item. This mode
implements iterative / scripted multi-step prompting, a manual,
externally-driven scaffold for stepwise reasoning. (It is distinct
from in-model zero-shot chain-of-thought, where stepwise reasoning is
elicited inside a single inference call by a prompt like "let's think
step by step"; here, the user-side scaffolding makes the steps
explicit and feeds each intermediate model output back as context for
the next user turn.) Example (scripted multi-step reasoning):
``["Step 1: identify objects.", "Step 2: describe relationships.",
"Step 3: conclude."]``: three sequential user prompts, three
inferences, final reply returned.

``turn-taking`` is the default because it costs a single inference call
and is the more common multi-element pattern.

Helpers
^^^^^^^

:meth:`~clams.app.ClamsPromptableApp.inject_promptable_parameters`
    A static method called from your app's ``appmetadata()`` (in
    ``metadata.py``) to add the SDK-managed promptable parameters.

:meth:`~clams.app.ClamsPromptableApp.build_conversation`
    Instance method that constructs a chat-template-compatible message
    list (or a ``List[List[dict]]`` of progressively-extending prefixes
    for ``user-only`` mode). Handles string and list prompt forms, the
    two ``promptMode`` semantics, the optional ``systemPrompt``, and
    inlines ``images`` / ``audios`` into the (final) user turn. Accepts
    a pre-built ``List[dict]`` and returns it unchanged. Subclasses
    may override to access model-specific state (e.g.
    ``self.processor``) when formatting messages.

:meth:`~clams.app.ClamsPromptableApp.response_to_grounded_textdocument`
    Writes a ``TextDocument`` plus an ``Alignment`` (``source -> TD``)
    into a view. ``source`` is the coarse cross-modal anchor; the
    optional ``origins`` (paired with ``origination``) is the finer
    derivation list, written to the TD's ``origins`` / ``origination``
    properties. See https://clams.ai/clams-vocabulary/Document for
    vocabulary semantics.

Backend helpers
^^^^^^^^^^^^^^^

The SDK provides optional helper utilities for loading common
inference backends, so apps don't have to write model-loading
boilerplate themselves. Backends are kept as separate subpackages
under ``clams.backends`` and their heavy dependencies are NOT pulled
in by the base ``clams-python`` install; you opt in via a pip extra
when your app needs the backend.

.. _backends-hf:

HuggingFace transformers (``clams.backends.hf``)
""""""""""""""""""""""""""""""""""""""""""""""""

:func:`clams.backends.hf.load_hf_model` loads any local HuggingFace
``transformers`` model via ``from_pretrained()`` and returns it ready
for inference. It encapsulates the device, processor/tokenizer, and
inference-mode boilerplate that every HF-backed app needs to do
identically:

- detects an available CUDA device and falls back to CPU when none is
  present
- loads the caller-supplied ``processor_cls`` (defaults to
  :class:`~transformers.AutoProcessor`; pass
  :class:`~transformers.AutoTokenizer`,
  :class:`~transformers.AutoImageProcessor`, etc. for narrower or
  more specific cases)
- loads the model via the caller-supplied ``model_cls``
- moves the model to the resolved device and switches it to ``eval()``
  mode
- when ``padding_side`` is given (decoder-only / batched-generation
  case), configures the tokenizer's padding side and uses the EOS
  token as the pad token; left as the model's own default otherwise

The function signature is::

    load_hf_model(
        model_id: str,
        model_cls,                              # e.g. AutoModelForCausalLM, AutoModelForImageTextToText, ConvNextV2Model, ViTModel, ...
        processor_cls = None,                   # default AutoProcessor; pass AutoTokenizer / AutoImageProcessor / ... for narrower cases, or None to skip processor loading
        dtype = None,                           # None leaves the model's own default (typically float32); set explicitly (e.g., torch.bfloat16) for LLMs
        device: Optional[str] = None,           # auto-detected when None
        padding_side: Optional[str] = None,     # set to 'left' for decoder-only batched generation; leave None for encoder / non-batched cases
        model_kwargs: Optional[dict] = None,    # extra kwargs forwarded to model_cls.from_pretrained()
        processor_kwargs: Optional[dict] = None,  # extra kwargs forwarded to processor_cls.from_pretrained()
    ) -> Tuple[processor, model, device_str]

The ``model_kwargs`` and ``processor_kwargs`` pass-throughs cover the
common ``from_pretrained()`` options that vary between model classes
and use cases: ``use_safetensors``, ``use_fast``,
``add_pooling_layer``, ``trust_remote_code``, ``revision``, etc.

An app's ``__init__`` typically calls this helper once and stores the
returned ``processor`` (or ``tokenizer`` / ``image_processor``),
``model``, and ``device`` on ``self`` for use inside its inference
method (e.g., :meth:`~clams.app.ClamsPromptableApp.generate`). See the
function's docstring for the full parameter reference and return
value.

Promptable apps wrapping a decoder-only / chat-tuned model typically
pass ``padding_side='left'`` and an explicit dtype like
``torch.bfloat16``; encoder-side HF apps (e.g., a vision feature
extractor + classifier head) leave both at the defaults and pass any
class-specific kwargs through ``model_kwargs`` /
``processor_kwargs``.

For promptable apps specifically, the
:class:`~clams.app.ClamsHFPromptableApp` base class (see
:ref:`hf-promptable`) wraps this helper plus the standard inference
loop, so most HF-backed VLM/LLM apps don't need to call
:func:`load_hf_model` directly.

Installation
~~~~~~~~~~~~

``torch`` and ``transformers`` are NOT included in the base
``clams-python`` install (to keep the SDK lightweight for apps that
don't need them). When your app uses the HF backend, install with the
``hf`` extra::

    pip install clams-python[hf]

The helper module imports ``torch`` and ``transformers`` lazily, so a
plain ``clams-python`` install can still import :mod:`clams.app` and
:class:`~clams.app.ClamsPromptableApp` without those dependencies; the
``ImportError`` only fires when an app actually calls
:func:`clams.backends.hf.load_hf_model`.

.. _hf-promptable:

HuggingFace Promptable Apps
---------------------------

For the very common case of "promptable CLAMS app + local HuggingFace
``transformers`` model," the SDK provides
:class:`~clams.app.ClamsHFPromptableApp`, a specialized subclass of
:class:`~clams.app.ClamsPromptableApp` that absorbs all HF-specific
inference boilerplate. Concrete apps inheriting from it declare the
model via a few class attributes and typically only need to implement
``_annotate()`` for their MMIF I/O.

When to use
^^^^^^^^^^^

Choose :class:`~clams.app.ClamsHFPromptableApp` over plain
:class:`~clams.app.ClamsPromptableApp` when your app:

- wraps a local HuggingFace ``transformers`` model loadable via
  ``from_pretrained()``, AND
- runs the standard chat-template -> ``model.generate`` ->
  ``batch_decode`` inference pipeline (every modern instruct-tuned
  VLM/LLM in HF), AND
- doesn't need bespoke pixel-value preprocessing or vision-token
  stitching at inference time.

If your app uses a remote API instead (OpenAI, Anthropic, etc.), or a
non-HF local backend, inherit from
:class:`~clams.app.ClamsPromptableApp` directly and implement
:meth:`~clams.app.ClamsPromptableApp.generate` yourself.

Class-attribute hooks
^^^^^^^^^^^^^^^^^^^^^

Concrete subclasses declare the model declaratively via class
attributes; the base ``__init__`` reads them, calls
:func:`load_hf_model`, and stores ``self.processor``, ``self.model``,
``self.device``:

.. list-table::
   :header-rows: 1
   :widths: 22 60 18

   * - Attribute
     - Meaning
     - Required
   * - ``MODEL_ID``
     - HuggingFace model identifier (Hub repo name or local path).
     - yes
   * - ``MODEL_CLS``
     - ``transformers`` model class (e.g.
       :class:`~transformers.AutoModelForImageTextToText`,
       :class:`~transformers.AutoModelForCausalLM`).
     - yes
   * - ``PROCESSOR_CLS``
     - Processor / tokenizer / feature-extractor class. Defaults to
       :class:`~transformers.AutoProcessor`.
     - no
   * - ``DTYPE``
     - Torch dtype for the model and for ``pixel_values`` casting in
       :py:meth:`~clams.app.ClamsHFPromptableApp.generate`. E.g.
       ``torch.bfloat16`` for low-precision LLM inference.
     - no
   * - ``PADDING_SIDE``
     - Tokenizer padding side. ``'left'`` for decoder-only batched
       generation; leave unset otherwise.
     - no
   * - ``MODEL_KWARGS`` / ``PROCESSOR_KWARGS``
     - Extra kwargs forwarded to the respective
       ``from_pretrained()`` calls (e.g.
       ``trust_remote_code=True``).
     - no

What the base class provides
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- A default :py:meth:`~clams.app.ClamsHFPromptableApp.__init__` that
  loads the model from the class attributes via
  :func:`load_hf_model`.
- A concrete :py:meth:`~clams.app.ClamsHFPromptableApp.generate` that
  satisfies the :class:`~clams.app.ClamsPromptableApp` abstract
  contract. Takes ``images`` / ``audios`` as ``List[List[Any]]``
  (N groups, one per prompt) and runs all N prompts in one HF
  forward pass; returns one decoded string per group. Apps call
  this from ``_annotate`` to run their inference; per-image
  broadcast is a singleton-wrap (``images=[[img] for img in
  images]``), per-TF composite is one group of N images per TF.
- A default
  :py:meth:`~clams.app.ClamsHFPromptableApp.build_gen_kwargs` that
  maps SDK promptable parameters (``maxNewTokens``, ``temperature``,
  ``topP``, ``topK``) into HF ``model.generate()`` kwargs.
  Subclasses may override to add model-specific kwargs
  (``num_beams``, ``repetition_penalty``, custom stopping criteria,
  etc.).

Minimal subclass example
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from transformers import AutoModelForImageTextToText
    import torch

    from clams.app import ClamsHFPromptableApp


    class MyVLMCaptioner(ClamsHFPromptableApp):
        MODEL_ID = "HuggingFaceTB/SmolVLM2-2.2B-Instruct"
        MODEL_CLS = AutoModelForImageTextToText
        DTYPE = torch.bfloat16
        PADDING_SIDE = 'left'

        def _appmetadata(self):
            pass  # defined in metadata.py

        def _annotate(self, mmif, **parameters):
            ...  # collect tasks from MMIF, build image groups, call
                 # self.generate(prompt, images=image_groups, ...), then
                 # store responses via self.response_to_grounded_textdocument

The ``metadata.py`` for an :class:`~clams.app.ClamsHFPromptableApp`
subclass is identical to a plain
:class:`~clams.app.ClamsPromptableApp` -- the helper-call requirement
and the parameter table are unchanged.
