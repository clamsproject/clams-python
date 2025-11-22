GPU Memory Management for CLAMS Apps
=====================================

This document covers GPU memory management features in the CLAMS SDK for developers building CUDA-based applications.

Overview
--------

CLAMS apps that use GPU acceleration face memory management challenges when running as HTTP servers with multiple workers. Each gunicorn worker loads models independently into GPU VRAM, which can cause out-of-memory (OOM) errors.

The CLAMS SDK provides:

1. **Metadata fields** for declaring GPU memory requirements
2. **Automatic worker scaling** based on available VRAM
3. **Worker recycling** to release GPU memory between requests
4. **Memory monitoring** via ``hwFetch`` parameter

.. note::
   Memory profiling features require **PyTorch** (``torch.cuda`` APIs). Worker calculation uses ``nvidia-smi`` and works with any framework.

Declaring GPU Memory Requirements
---------------------------------

Declare GPU memory requirements in app metadata:

.. list-table::
   :header-rows: 1
   :widths: 15 10 10 65

   * - Field
     - Type
     - Default
     - Description
   * - ``est_gpu_mem_min``
     - int
     - 0
     - Memory usage with parameters set for least computation (e.g., smallest model). 0 means no GPU.
   * - ``est_gpu_mem_typ``
     - int
     - 0
     - Memory usage with default parameters. Used for worker calculation.

These values don't need to be precise. A reasonable estimate from development experience (e.g., observing ``nvidia-smi`` during runs) is sufficient.

Example:

.. code-block:: python

   metadata = AppMetadata(
       name="My GPU App",
       # ... other fields
       est_gpu_mem_min=4000,  # 4GB minimum
       est_gpu_mem_typ=6000,  # 6GB typical
   )

Gunicorn Integration
--------------------

Running ``python app.py --production`` starts a gunicorn server with automatic GPU-aware configuration.

Worker Calculation
~~~~~~~~~~~~~~~~~~

Worker count is the minimum of:

- CPU-based: ``(cores × 2) + 1``
- VRAM-based: ``total_vram / est_gpu_mem_typ``

Override with ``CLAMS_GUNICORN_WORKERS`` environment variable if needed.

Worker Recycling
~~~~~~~~~~~~~~~~

By default, workers are recycled after each request (``max_requests=1``) to fully release GPU memory. For single-model apps, disable recycling for better performance:

.. code-block:: python

   restifier.serve_production(max_requests=0)  # Workers persist

NVIDIA Memory Oversubscription
------------------------------

.. warning::
   **NVIDIA drivers R535+ include "System Memory Fallback"** - when VRAM is exhausted, the GPU swaps to system RAM via PCIe. This prevents OOM errors but causes **severe performance degradation (5-10x slower)**.

   This feature is convenient for development but can mask memory issues in production. Monitor actual VRAM usage with ``hwFetch`` to ensure your app fits in GPU memory.

Disabling Oversubscription
~~~~~~~~~~~~~~~~~~~~~~~~~~

To force OOM errors instead of silent performance degradation:

**PyTorch:**

.. code-block:: python

   import torch
   # Limit to 90% of VRAM - will raise OOM if exceeded
   torch.cuda.set_per_process_memory_fraction(0.9)

**TensorFlow:**

.. code-block:: python

   import tensorflow as tf
   gpus = tf.config.list_physical_devices('GPU')
   if gpus:
       # Set hard memory limit (in MB)
       tf.config.set_logical_device_configuration(
           gpus[0],
           [tf.config.LogicalDeviceConfiguration(memory_limit=8000)]
       )

Monitoring with hwFetch
-----------------------

Enable ``hwFetch`` parameter to include GPU info in responses:

.. code-block:: bash

   curl -X POST "http://localhost:5000/?hwFetch=true" -d@input.mmif

Response includes::

   NVIDIA RTX 4090, 23.65 GiB total, 20.00 GiB available, 3.50 GiB peak used

Use this to verify your app's actual VRAM usage and tune ``est_gpu_mem_typ`` accordingly.
