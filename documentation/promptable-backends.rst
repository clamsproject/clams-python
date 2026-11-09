.. _promptable-backends:

HF and GGUF Promptable Apps
===========================

The SDK has two backends for promptable apps:
:class:`~clams.app.ClamsHFPromptableApp` runs a Hugging Face
``transformers`` model in the app process, and
:class:`~clams.app.ClamsGGUFPromptableApp` (experimental) runs a GGUF
model in a ``llama-server`` process that the app starts and owns. Both
share the promptable runtime parameters, the ``model`` parameter
derived from ``analyzer_versions``, and the output format. This page
lists where they differ. For how to declare each, see
:ref:`hf-promptable` and :ref:`gguf-promptable`.

The primary target is NVIDIA GPUs with CUDA: the container images ship
the latest release of each backend, built with CUDA support.

.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * -
     - HF (``ClamsHFPromptableApp``)
     - GGUF (``ClamsGGUFPromptableApp``)
   * - Inference engine
     - ``torch`` and ``transformers``, in the app process
     - ``llama-server`` (llama.cpp), a child process on localhost
   * - Python extra
     - ``[hf]``
     - ``[llamaserver]``, plus a ``llama-server`` executable
   * - Container image
     - ``clams-python-hf5`` and its ``ffmpeg`` / ``opencv4`` variants
     - ``clams-python-llamaserver``, built on llama.cpp's CUDA image
   * - Model id in ``analyzer_versions``
     - ``<repo>``, refined to ``<repo>@<revision>``
     - ``<repo>:<quantization>``, refined to
       ``<repo>:<quantization>@<revision>``
   * - Model files
     - the repository snapshot, loaded with ``from_pretrained()``
     - one GGUF file (or its shards) and, for vision input, one
       ``mmproj`` file, picked by the quantization tag or
       ``MODEL_FILES``
   * - Hardware
     - NVIDIA GPUs that the latest ``torch`` supports: Turing and
       newer, since ``torch`` 2.15 dropped Maxwell, Pascal and Volta.
       Falls back to CPU.
     - NVIDIA GPUs that llama.cpp's CUDA build supports, including
       older ones: tested on Maxwell. Falls back to CPU.
   * - Model placement
     - one device (the first GPU, or CPU), unless ``MODEL_KWARGS``
       sets a ``device_map``
     - the server places what fits on the visible GPUs and keeps the
       rest in system memory
   * - Hardware settings
     - class attributes (``DTYPE``, ``MODEL_KWARGS``) set by the app
       developer
     - ``LLAMA_ARG_*`` environment variables: defaults in the app's
       ``LLAMA_ARGS``, overridden by the deployment. Note that these
       variables are not recorded in the output MMIF; the settings in
       effect appear only in the app log.
   * - Prompts run together
     - ``parallelPrompts`` runtime parameter, per request; the prompts
       are padded into one batch
     - the server's slot count, fixed when the server starts (one
       recommended); no ``parallelPrompts`` parameter
   * - Memory for one request
     - grows with ``parallelPrompts`` and the prompt size; too much
       runs the GPU out of memory
     - fixed when the server starts; how the slots share the context
       depends on the llama.cpp release
   * - Prompt too large
     - out-of-memory error
     - context-size error (an error view naming the context size)
   * - Production mode
     - workers by CPU count and ``est_gpu_mem_typ``, each replaced
       after one request
     - one worker, never replaced
       (``RESTIFIER_PRODUCTION_WORKERS``,
       ``RESTIFIER_PRODUCTION_MAX_REQUESTS``)
   * - ``hwFetch`` profiling
     - GPU name, total, available and peak memory
     - GPU name and total memory only
   * - Audio input
     - supported, if the model takes audio
     - not supported
   * - Status
     - stable
     - experimental

Two differences matter most when moving an app from one backend to the
other.

Who sets the batch size
-----------------------

An HF app takes ``parallelPrompts`` with each request and stacks that
many prompts into one forward pass. A GGUF app sends as many prompts
at a time as ``llama-server`` has slots, and the server decodes them
together. The slot count is a server setting, fixed when the server
starts; see :ref:`gguf-promptable` for the recommended value. An app
moved to the GGUF backend must stop reading
``parameters['parallelPrompts']`` and stop passing ``parallel_prompts`` to
:meth:`~clams.app.ClamsGGUFPromptableApp.generate_batched`.

Outputs differ between backends
-------------------------------

A GGUF file is a converted, usually quantized, copy of the original
model, and llama.cpp computes with different kernels. The same model
gives different outputs on the two backends, even at temperature 0.
With more than one slot, GGUF outputs can also shift slightly with the
other prompts decoded at the same time. Compare outputs before you
replace an HF app with a GGUF one.
