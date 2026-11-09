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

   ``ClamsPromptableApp`` assumes an **instruction- or chat-tuned**
   model with a system/user/assistant role structure. Bare completion
   / next-token-prediction base models do not fit this base class
   cleanly; use :class:`~clams.app.ClamsApp` directly for those.

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
   * - ``useReasoning``
     - boolean
     - ``false``
     - no
     - Request the model's reasoning ("thinking") mode. Off by default;
       honored only by apps whose model has a distinct reasoning mode
       (others ignore it). Much slower and more token-hungry -- the trace is
       generated before the answer and drawn from the ``maxNewTokens`` budget,
       and small models can loop without terminating. When honored, the trace
       is stored in the ``modelReasoningTrace`` property of the output
       ``TextDocument``. See :ref:`promptable-reasoning`.
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
     - Number of independent prompts the app stacks into a single
       forward pass. Per-prompt content size is the app's
       responsibility; prompt count and per-prompt size combine
       multiplicatively for GPU memory. Keep at ``1`` on memory-tight
       setups; see the parameter's own description in
       :py:attr:`~clams.app.ClamsPromptableApp.promptable_parameters`
       for an OOM-risk example.
   * - ``maxImagesPerPrompt``
     - integer
     - ``0``
     - no
     - Maximum number of images the app bundles into a single prompt (one
       generation, one output ``TextDocument``). ``0`` means no limit. With a
       positive value, the app splits a TimeFrame with more frames into
       consecutive capped groups, each producing its own ``TextDocument``
       aligned to that TimeFrame and grounded via ``origins``. Bounds GPU
       memory for long dynamic scenes; composes with ``parallelPrompts``.
   * - ``imagesPerPromptMode``
     - string
     - ``max``
     - no
     - How the images of a TimeFrame over ``maxImagesPerPrompt`` are spread
       over its prompts; no effect when the cap is ``0``. ``max`` fills each
       prompt to the cap and leaves the remainder last. ``balanced`` spreads
       the images evenly. Both give the same number of prompts.

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

A promptable app requires two paired edits relative to the scaffold
generated by ``clams develop``:

1. In ``app.py``, change the app class's base from
   :class:`~clams.app.ClamsApp` to
   :class:`~clams.app.ClamsPromptableApp` and implement
   :meth:`~clams.app.ClamsPromptableApp.generate`. The scaffold file
   already contains a guiding comment at the class declaration line.
2. In ``metadata.py``, call
   :meth:`ClamsPromptableApp.inject_promptable_parameters
   <clams.app.ClamsPromptableApp.inject_promptable_parameters>` at
   the end of ``appmetadata()``. The scaffold file already contains
   a commented-out helper-call block; uncomment it.

The ``__main__`` block in ``metadata.py`` is unchanged from
non-promptable apps. The helper call inside ``appmetadata()`` makes
the promptable parameters visible to both ``python metadata.py``
(build-time discovery) and to
:meth:`~clams.app.ClamsApp._load_appmetadata` (runtime). The base
class change ensures the app inherits the parameter-presence
validation, the ``generate()`` contract, and the helper methods at
runtime.

The ``generate()`` contract
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Subclasses of :class:`~clams.app.ClamsPromptableApp` that wrap a backend
without a default SDK implementation (e.g., remote-API or custom local
backends) MUST implement :meth:`~clams.app.ClamsPromptableApp.generate`.
Subclasses of :class:`~clams.app.ClamsHFPromptableApp` inherit a concrete
``generate()`` and do not need to override it. See the method's docstring
for the full signature, batch semantics, and return value.

Keep inference logic inside ``generate()`` distinct from MMIF I/O; the
latter belongs in ``_annotate()`` (which calls ``self.generate()``).
This separation lets HF-backed apps inherit the default ``generate()``
without restating backend mechanics, and lets non-HF apps swap in a new
``generate()`` without rewriting their MMIF I/O.

.. _promptable-grouping:

From TimeFrames to forward passes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Three parameters group the visual input at three different steps. The
documentation and the helper names use one word for each step.

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Step
     - Parameter
     - Word
   * - TimeFrame to frames
     - ``tfSamplingMode``
     - sample
   * - One TimeFrame's frames to prompts
     - ``maxImagesPerPrompt``, ``imagesPerPromptMode``
     - chunk
   * - Prompts to forward passes
     - ``parallelPrompts``
     - batch

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

.. _promptable-reasoning:

Reasoning traces (``useReasoning``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Some models expose a distinct reasoning ("thinking") mode that emits an
intermediate reasoning trace before the answer. ``useReasoning`` is the
standard toggle for that mode. It is inert unless the app honors it, and
honoring is a per-app choice with three wiring points:

- map ``useReasoning`` onto the backend's reasoning switch (for HF chat
  templates, typically ``enable_thinking``) by overriding
  :meth:`~clams.app.ClamsHFPromptableApp.build_template_kwargs`;
- split the trace from the answer with
  :meth:`~clams.app.ClamsPromptableApp.split_tagged_reasoning_trace`
  (inline ``<think>...</think>``-style traces only; channel-delimited
  formats need app-specific parsing). Many chat templates prefill the
  opening ``<think>`` into the prompt, so only the closing tag appears in
  the output; pass ``assume_open=True`` (wired to the reasoning toggle) so
  the trace is still recovered and a missing close tag is read as
  unterminated reasoning (empty answer) rather than a plain answer;
- pass the trace to
  :meth:`~clams.app.ClamsPromptableApp.response_to_grounded_textdocument`
  through its ``reasoning_trace`` argument, which stores it in the
  ``modelReasoningTrace`` property of the produced ``TextDocument``,
  separate from the document text.

An app whose model has no reasoning mode leaves ``useReasoning`` unwired;
callers may still set it and it has no effect, like ``topK`` under greedy
decoding.

Cost and failure modes
""""""""""""""""""""""

Reasoning is much slower and far more token-hungry than a direct answer:
the entire trace is generated first, from the same budget capped by
``maxNewTokens``. Enabling ``useReasoning`` without raising ``maxNewTokens``
substantially (thousands of tokens, not hundreds) risks the trace consuming
the whole budget, leaving the answer truncated or empty. Small reasoning
models (as a rule of thumb, roughly 4B parameters and under) are especially
prone to non-terminating "thinking loops" that never reach an answer; budget
generously and validate termination per model. When the trace overruns the
budget before closing, ``assume_open=True`` yields an empty answer plus the
unterminated trace -- an app should surface that (e.g. a warning and an empty
``TextDocument``) rather than emitting the raw reasoning as the answer.

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

:meth:`~clams.app.ClamsPromptableApp.chunk_tasks`
    A static method that applies ``maxImagesPerPrompt``: splits each
    :class:`~clams.app.PromptTask` (images, their ``origins``, and the
    anchoring ``source``) with more images than the cap into consecutive
    capped tasks. Each task yields one ``TextDocument``, so with a cap
    set, one TimeFrame can yield several ``TextDocument`` annotations
    aligned to it, each grounded to its own ``origins``. Consumers of
    promptable-app output must not assume one ``TextDocument`` per
    TimeFrame. ``imagesPerPromptMode``
    (:class:`~clams.app.ImagesPerPromptMode`) selects how the images are
    spread over the chunks.

:meth:`~clams.app.ClamsPromptableApp.generate_batched`
    Applies ``parallelPrompts``: calls ``generate()`` on batches of at
    most that many prompts and returns one output per prompt, in order.

:meth:`~clams.app.ClamsPromptableApp.report_progress`
    Called by ``generate_batched()`` before the first batch and after
    each batch with the number of prompts done and the total. The
    default writes one INFO log line; override it to report differently
    or to stay silent.

:meth:`~clams.app.ClamsPromptableApp.response_to_grounded_textdocument`
    Writes a ``TextDocument`` plus an ``Alignment`` (``source -> TD``)
    into a view. ``source`` is the coarse cross-modal anchor; the
    optional ``origins`` (paired with ``origination``) is the finer
    derivation list, written to the TD's ``origins`` / ``origination``
    properties. See https://clams.ai/clams-vocabulary/Document for
    vocabulary semantics.

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

For a model in GGUF format run with llama.cpp, see
:ref:`gguf-promptable` (experimental). If your app uses a remote API
instead (OpenAI, Anthropic, etc.), or another local backend, inherit
from :class:`~clams.app.ClamsPromptableApp` directly and implement
:meth:`~clams.app.ClamsPromptableApp.generate` yourself.

.. _hf-promptable-declaring:

Declaring an HF promptable app
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

On top of the baseline declaration shared by every promptable app
(see :ref:`promptable-declaration`), a
:class:`~clams.app.ClamsHFPromptableApp` subclass:

1. Uses :class:`~clams.app.ClamsHFPromptableApp` (not
   :class:`~clams.app.ClamsPromptableApp`) as the base class in
   ``app.py``.
2. Declares the required class attribute ``MODEL_CLS`` and any
   optional dtype / padding / kwargs hints (see
   :ref:`hf-promptable-class-attrs` for the full list).
3. Sets ``analyzer_versions={<hf-id>: <commit-hash>, ...}`` on the
   ``AppMetadata`` constructor call in ``metadata.py`` (replaces the
   singular ``analyzer_version`` for HF apps).
4. Calls
   :meth:`ClamsHFPromptableApp.inject_promptable_parameters
   <clams.app.ClamsHFPromptableApp.inject_promptable_parameters>`
   (the HF override of the plain helper) at the end of
   ``appmetadata()``. The scaffold ``metadata.py`` contains a
   commented-out HF block; uncomment it.
5. Inherits the base class's
   :meth:`~clams.app.ClamsPromptableApp.generate` implementation;
   no override needed.

For a minimal worked example, see the class docstring on
:class:`~clams.app.ClamsHFPromptableApp`.

.. _hf-promptable-class-attrs:

Class-attribute hooks
^^^^^^^^^^^^^^^^^^^^^

Concrete subclasses declare the model class plus optional dtype /
padding hints via class attributes, and declare the family of
supported model variants (with pinned commits) via
``analyzer_versions`` in ``metadata.py``:

.. list-table::
   :header-rows: 1
   :widths: 22 60 18

   * - Attribute
     - Meaning
     - Required
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

The HF model identifiers themselves are NOT a class attribute. They
live in ``metadata.py`` as ``analyzer_versions``, a
``Dict[str, str]`` mapping each supported model id to its pinned
commit hash. The SDK auto-derives a ``model`` runtime parameter
from this dict, with ``choices`` set to the dict keys.

Family / singleton handling
^^^^^^^^^^^^^^^^^^^^^^^^^^^

When ``analyzer_versions`` contains a single entry (the typical
single-model app), the SDK eagerly pre-loads that one model in
``__init__`` and sets ``model.default`` to the only key so callers
can omit the parameter. Single-model apps thus preserve warm-start
semantics: the model is loaded at app startup, not on first request.

When ``analyzer_versions`` contains multiple entries (a family app),
loading is deferred until the first :py:meth:`load_model` call inside
``_annotate``, and ``model`` has no default by default; callers
must pick a family member explicitly (or the dev mutates
``model.default`` post-injection to provide a recommended pick).
Loaded models are cached per ``(model_id, revision)`` for the
lifetime of the app instance; switching models loads on first miss,
cache-hits on repeat.

Reproducibility: ``model`` refinement and view metadata
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The user-facing ``model`` parameter accepts raw HF model ids
(``org/repo-name``). The SDK's
:py:meth:`~clams.app.ClamsPromptableApp._refine_params` expands the
raw value to ``org/repo-name@<revision>`` form (using the dict
lookup) during parameter refinement. The standard ``sign_view`` flow
then stamps:

- the **raw** user choice into ``view.metadata.parameters['model']``
  (transparency: what the user typed),
- the **resolved** ``org/repo-name@<revision>`` into
  ``view.metadata.appConfiguration['model']`` (reproducibility: the
  exact commit applied).

A consumer of the output MMIF can read the resolved revision directly
from the view metadata, with no cross-reference to the app metadata
required.

This ``model`` handling is a specific instance of the general MMIF convention
for recording runtime configuration; see the view-metadata section of the
`MMIF specification <https://mmif.clams.ai/1.2.0/>`_ for the definitions of the
``parameters`` and ``appConfiguration`` fields.

What the base class provides
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A subclass typically only writes ``_annotate()``. The base class
supplies:

* model loading and caching via
  :py:meth:`~clams.app.ClamsHFPromptableApp.load_model`, which wraps
  :func:`clams.backends.hf.load_hf_model` (non-promptable HF apps
  can call that loader directly without going through this base
  class);
* the parameter injector
  :py:meth:`ClamsHFPromptableApp.inject_promptable_parameters
  <clams.app.ClamsHFPromptableApp.inject_promptable_parameters>`;
* a concrete batched HF
  :py:meth:`~clams.app.ClamsHFPromptableApp.generate`;
* a default
  :py:meth:`~clams.app.ClamsHFPromptableApp.build_gen_kwargs` that
  maps the SDK promptable parameters to HF ``model.generate()``
  kwargs;
* a :py:meth:`~clams.app.ClamsHFPromptableApp.build_template_kwargs`
  hook for chat-template controls, the override point for honoring
  ``useReasoning`` (see :ref:`promptable-reasoning`).

See each method's docstring for full details.

Apps using the HF backend (with or without the promptable wrapper)
must install the ``[hf]`` extra: ``pip install clams-python[hf]``.

.. _gguf-promptable:

GGUF Promptable Apps (experimental)
-----------------------------------

:class:`~clams.app.ClamsGGUFPromptableApp` runs a model in GGUF format
with `llama.cpp <https://github.com/ggml-org/llama.cpp>`_ instead of
``transformers``. The app owns a private ``llama-server`` process: it
downloads the pinned GGUF file (and the ``mmproj`` projector file of a
vision model) from the Hugging Face Hub, starts the server on a free
localhost port, sends prompts through the server's OpenAI-compatible
chat API, and stops the server when the app exits. The app never
connects to a server it did not start, so model selection stays with
the app and is recorded in the output MMIF as for an HF app.

This backend is experimental. Its class attributes and the container
image may change between releases.

When to use
^^^^^^^^^^^

Choose :class:`~clams.app.ClamsGGUFPromptableApp` when the app should
run without ``torch``: a quantized model on a small GPU, a GPU that
current ``torch`` wheels no longer support, or CPU-only inference. The
same model in GGUF form gives different output than its ``transformers``
original, so an app that must reproduce an HF app's output stays with
:class:`~clams.app.ClamsHFPromptableApp`.

Declaring a GGUF promptable app
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The declaration follows :ref:`hf-promptable-declaring`, with these
differences:

1. ``analyzer_versions`` keys are ``<hub repo>`` or
   ``<hub repo>:<quantization>`` (e.g.
   ``ggml-org/gemma-4-E4B-it-GGUF:Q8_0``), and the values are commit
   hashes of the GGUF repository. The quantization tag picks the model
   file, and the repository's ``mmproj`` file is picked for vision
   input.
2. ``MODEL_FILES`` names the files explicitly for a repository where the
   tag does not pick exactly one file (several projectors, draft
   models, shards).
3. ``metadata.py`` calls
   :meth:`ClamsGGUFPromptableApp.inject_promptable_parameters
   <clams.app.ClamsGGUFPromptableApp.inject_promptable_parameters>`.

The ``model`` parameter, family and singleton handling, and the
``model`` refinement into ``appConfiguration`` work as for HF apps.
Audio input is not supported yet.

GGUF apps have no ``parallelPrompts`` parameter. ``llama-server``
decodes at most as many requests together as it has slots, a number
fixed when the server starts, and
:meth:`~clams.app.ClamsGGUFPromptableApp.generate_batched` keeps every
slot busy. The slot count is a server setting (see below), and its
default, like the way slots share the context, belongs to llama.cpp
and changes between its releases; see the llama.cpp documentation. The
startup log reports the slot count and the context of a slot.

We recommend one slot, set in the app's ``LLAMA_ARGS``. The server
decodes the prompts in its slots together, so with more slots an
output can change with the other prompts in flight. In our tests on
Maxwell and Pascal GPUs, more slots were also no faster.

Class-attribute hooks
^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 22 60 18

   * - Attribute
     - Meaning
     - Required
   * - ``MODEL_FILES``
     - File names per model id: ``{'<id>': {'model': '<file>' or
       [shards], 'mmproj': '<file>'}}``. Models not listed are
       resolved from the repository listing.
     - no
   * - ``LLAMA_ARGS``
     - Default values of llama.cpp's ``LLAMA_ARG_*`` environment
       variables for what the app's models need, e.g. a larger batch
       size for the image tokens of a vision model, or the slot count.
       The environment of the app process takes precedence (see
       below).
     - no
   * - ``RESTIFIER_PRODUCTION_WORKERS``,
       ``RESTIFIER_PRODUCTION_MAX_REQUESTS``
     - Read only by :meth:`~clams.restify.Restifier.serve_production`
       (no effect in the CLI): one gunicorn worker, never recycled, so
       the server the app owns is neither duplicated nor restarted per
       request. A singleton app starts its server before gunicorn
       forks, so all workers share it; a family app starts one server
       per worker.
     - no

Server settings
^^^^^^^^^^^^^^^

The SDK gives ``llama-server`` only the model files, its address and
the reasoning output format on the command line. Every other setting
is one of llama.cpp's own ``LLAMA_ARG_*`` environment variables, which
the server reads for every argument not on its command line. A value
comes from, in increasing precedence:

1. ``llama-server``'s defaults, which fit the run to the hardware: GPU
   offload, context size, batch sizes, threads and the split over
   several GPUs. The server places what fits on the GPUs, keeps the
   rest in system memory, and sizes the context to the free memory.
1. The app's ``LLAMA_ARGS``, for what its models need.
1. The environment of the app process, set by whoever runs the app.

The variables and their defaults belong to llama.cpp and change
between its releases; see the llama.cpp documentation. The settings in
effect are logged with their source when the server starts, and the
context size and slot count when it is ready.

One prompt (system and user text, all its images, and the generated
tokens) must fit in the context of a server slot. A prompt that does
not fails the request with an error naming the size, so a caller can
lower ``maxImagesPerPrompt`` or give the server a larger context.

Installation and containers
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The python side needs the ``[llamaserver]`` extra:
``pip install clams-python[llamaserver]``. The ``llama-server``
executable is not a python package: outside a container, put it on the
``PATH`` or name it in the ``LLAMA_SERVER`` environment variable.

The ``clams-python-llamaserver`` container image provides it. The image
is built on llama.cpp's own CUDA server image, so it has no ``torch``
and does not derive from the other ``clams-python`` images. Mount a
volume at ``/cache`` for the downloaded model and for the CUDA kernels
the driver compiles at the first start on GPUs the image has no machine
code for.

