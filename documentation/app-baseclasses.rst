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
   * - ``runningTime
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
   * - ``batchSize``
     - integer
     - ``1``
     - no
     - How many input items the app groups per ``generate`` call. GPU memory
       scales roughly linearly with batch size; raise for throughput on
       GPUs with headroom, keep at ``1`` on memory-tight setups.

.. _promptable-customizing-defaults:

Customizing default values
""""""""""""""""""""""""""

The SDK ships sensible defaults for most promptable parameters but
deliberately leaves ``prompt`` **without** a default; prompts are
inherently app-specific and no single value is right for all apps.
Beyond ``prompt``, other defaults may also be inappropriate for a given
app: a model that needs longer outputs wants a higher ``maxNewTokens``,
a small-VRAM deployment wants ``batchSize`` pinned at ``1``, etc.

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

The return value is a flat ``List[str]``: one entry per input item (one per
image when ``images`` is given, one per audio clip when ``audio`` is given,
or a single-element list for text-only single-shot generation). Keep
inference logic inside ``generate()`` distinct from MMIF I/O; the latter
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
    Instance method that constructs a chat-template-compatible message list
    (or list of message lists for ``user-only`` mode). Subclasses may
    override to access model-specific state (e.g. ``self.processor``).
    Currently a stub; a default implementation is planned for a follow-up
    release.

:meth:`~clams.app.ClamsPromptableApp.store_response`
    Helper for the common annotation-creation pattern: given a view, a
    source annotation's ``long_id``, and a generated string, creates a
    ``TextDocument`` containing the text plus an ``Alignment`` linking
    source to TextDocument; returns the ``(text_document, alignment)``
    pair. The optional ``trace`` parameter is reserved for
    reasoning-trace storage; passing a non-``None`` value currently
    raises :class:`NotImplementedError` (storage convention tracked in
    clamsproject/clams-python#263).

Backend helpers
^^^^^^^^^^^^^^^

For apps wrapping a local HuggingFace transformers model, the SDK provides
a loading helper in ``clams.backends.hf``. *Documentation for the HF
backend helper will be added in a follow-up release; see
clamsproject/clams-python#263 for status.*
