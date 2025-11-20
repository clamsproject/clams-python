# Issue #243 Investigation: GPU Memory Management in CLAMS SDK

**Issue**: https://github.com/clamsproject/clams-python/issues/243
**Status**: Investigation Complete - SDK-Level Solution Proposed
**Date**: 2025-01-08

---

## Executive Summary

When CLAMS applications using PyTorch models run in production mode (gunicorn), each worker process independently loads models into GPU VRAM. This leads to excessive memory consumption that scales with worker count, causing OOM errors.

**Root Cause**: Gunicorn's multi-process architecture combined with VRAM being a shared, dynamic resource that cannot be allocated statically.

**Proposed Solution**: SDK-level VRAM management through runtime checking and unified API, rather than fragmented app-level implementations.

---

## Problem Analysis

### Current Architecture

**Production Configuration** (`clams/restify/__init__.py:42-78`):
- Workers: `(CPU_count × 2) + 1`
- Threads per worker: 2
- Worker class: sync (default)

On an 8-core machine: **17 workers**

**Model Loading Pattern** (from templates and existing apps):
```python
class MyApp(ClamsApp):
    def __init__(self):
        super().__init__()
        # Option A: Load in __init__ (pre-fork) - BAD
        # self.model = torch.load('model.pt')

        # Option B: Load on-demand in _annotate() - BETTER but still problematic
        self.models = {}

    def _annotate(self, mmif, **parameters):
        if model_name not in self.models:
            self.models[model_name] = torch.load('model.pt')  # Each worker loads independently
        # ...
```

### Why This Causes Issues

**Multi-Worker Duplication**:
```
Worker 1: Loads model on first request → 3GB VRAM
Worker 2: Loads model on first request → 3GB VRAM
...
Worker 17: Loads model on first request → 3GB VRAM

Total: 17 × 3GB = 51GB VRAM required
```

**VRAM is a Shared, Dynamic Resource**:
- Other applications can allocate VRAM at any time
- Cannot assume static VRAM availability at startup
- Must check availability at runtime before loading

**Process Isolation**:
- Each gunicorn worker is a separate OS process
- CUDA contexts are process-isolated (no shared GPU memory)
- Workers cannot share model instances in VRAM

### Real-World Impact

**Example: Whisper Wrapper** (`app-whisper-wrapper/app.py`)

The app attempts mitigation by:
1. Loading models on-demand (not in `__init__()`)
2. Caching models per worker
3. "Conflict prevention" that loads duplicate models if one is in use

**Problems**:
- Still loads one model per worker over time (51GB for 17 workers)
- Conflict prevention can load duplicates within same worker (102GB worst case)
- No awareness of VRAM availability from other processes

---

## Proposed SDK-Level Solution

### Design Principles

1. **Centralized Management**: SDK handles VRAM checking, not individual apps
2. **Runtime Checking**: Check VRAM availability at request time, not startup
3. **Fail Fast**: Return clear errors when VRAM unavailable
4. **Backward Compatible**: Existing apps continue working without changes
5. **Opt-In Enhancement**: Apps can declare requirements for better behavior

### Architecture Overview

```
Request Flow:
  HTTP POST → ClamsHTTPApi.post()
    → ClamsApp.annotate()
      → _profile_cuda_memory() decorator
        → Check VRAM requirements (NEW)
        → Call _annotate() if sufficient VRAM
        → torch.cuda.empty_cache() cleanup (EXISTING)
```

### Component 1: Model Requirements API

**Apps declare their model memory needs:**

```python
# clams/app/__init__.py - Add to ClamsApp base class

class ClamsApp(ABC):

    def _get_model_requirements(self, **parameters) -> Optional[dict]:
        """
        Declare model memory requirements based on runtime parameters.

        Apps override this to enable VRAM checking.

        :param parameters: Runtime parameters from the request
        :return: Dict with 'size_bytes' and optional 'name', or None

        Example:
            def _get_model_requirements(self, **parameters):
                model_sizes = {'small': 2*1024**3, 'large': 6*1024**3}
                model = parameters.get('model', 'small')
                return {'size_bytes': model_sizes[model], 'name': model}
        """
        return None  # Default: no specific requirements
```

**App Implementation Example** (whisper-wrapper):
```python
class WhisperWrapper(ClamsApp):

    MODEL_SIZES = {
        'tiny': 500 * 1024**2,
        'base': 1024 * 1024**2,
        'small': 2 * 1024**3,
        'medium': 3 * 1024**3,
        'large': 6 * 1024**3,
        'large-v2': 6 * 1024**3,
        'large-v3': 6 * 1024**3,
        'turbo': 3 * 1024**3,
    }

    def _get_model_requirements(self, **parameters):
        size = parameters.get('model', 'medium')
        if size in self.model_size_alias:
            size = self.model_size_alias[size]

        return {
            'size_bytes': self.MODEL_SIZES.get(size, 3 * 1024**3),
            'name': size
        }
```

### Component 2: Runtime VRAM Checking

**Enhance existing `_profile_cuda_memory()` decorator:**

```python
# clams/app/__init__.py:349-392 - Enhanced version

@staticmethod
def _profile_cuda_memory(func):
    """
    Decorator for profiling CUDA memory usage and managing VRAM availability.
    """
    def wrapper(self, *args, **kwargs):
        cuda_profiler = {}
        torch_available = False
        cuda_available = False

        try:
            import torch
            torch_available = True
            cuda_available = torch.cuda.is_available()
        except ImportError:
            pass

        # NEW: Runtime VRAM checking before execution
        if torch_available and cuda_available:
            # Get model requirements from app
            requirements = self._get_model_requirements(**kwargs)

            if requirements:
                required_bytes = requirements['size_bytes']
                model_name = requirements.get('name', 'model')

                # Check if sufficient VRAM available RIGHT NOW
                if not ClamsApp._check_vram_available(required_bytes):
                    available_gb = ClamsApp._get_available_vram() / 1024**3
                    required_gb = required_bytes / 1024**3

                    error_msg = (
                        f"Insufficient GPU memory for {model_name}. "
                        f"Required: {required_gb:.2f}GB, "
                        f"Available: {available_gb:.2f}GB. "
                        f"GPU may be in use by other processes. "
                        f"Please retry later."
                    )
                    self.logger.error(error_msg)
                    raise RuntimeError(error_msg)

                self.logger.info(
                    f"VRAM check passed for {model_name}: "
                    f"{required_gb:.2f}GB required, "
                    f"{ClamsApp._get_available_vram() / 1024**3:.2f}GB available"
                )

            # Reset peak memory stats
            torch.cuda.reset_peak_memory_stats('cuda')

        try:
            result = func(self, *args, **kwargs)

            # Record peak memory usage (EXISTING)
            if torch_available and cuda_available:
                device_count = torch.cuda.device_count()
                for device_id in range(device_count):
                    device_id_str = f'cuda:{device_id}'
                    peak_memory = torch.cuda.max_memory_allocated(device_id_str)
                    gpu_name = torch.cuda.get_device_name(device_id_str)
                    gpu_total = torch.cuda.get_device_properties(device_id_str).total_memory
                    key = ClamsApp._cuda_device_name_concat(gpu_name, gpu_total)
                    cuda_profiler[key] = peak_memory

            return result, cuda_profiler
        finally:
            # Cleanup (EXISTING)
            if torch_available and cuda_available:
                torch.cuda.empty_cache()

    return wrapper

@staticmethod
def _check_vram_available(required_bytes, safety_margin=0.1):
    """
    Check if sufficient VRAM is available at this moment.

    :param required_bytes: Bytes needed for model
    :param safety_margin: Fraction of total VRAM to keep as headroom (default 10%)
    :return: True if sufficient VRAM available
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return True  # No CUDA, no constraints

        device = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(device)
        total_vram = props.total_memory

        # Get currently allocated/reserved memory
        allocated = torch.cuda.memory_allocated(device)
        reserved = torch.cuda.memory_reserved(device)
        used = max(allocated, reserved)

        # Calculate available VRAM RIGHT NOW
        available = total_vram - used

        # Apply safety margin
        required_with_margin = required_bytes + (total_vram * safety_margin)

        return available >= required_with_margin

    except Exception:
        # If we can't check, fail open (allow the request)
        return True

@staticmethod
def _get_available_vram():
    """Get currently available VRAM in bytes"""
    try:
        import torch
        if not torch.cuda.is_available():
            return 0

        device = torch.cuda.current_device()
        total = torch.cuda.get_device_properties(device).total_memory
        used = max(torch.cuda.memory_allocated(device),
                   torch.cuda.memory_reserved(device))
        return total - used
    except:
        return 0
```

### Component 3: Conservative Worker Count

**Adjust default worker calculation when CUDA detected:**

```python
# clams/restify/__init__.py:51-52 - Modified

def number_of_workers():
    """
    Calculate workers considering GPU constraints.
    Use conservative count when CUDA available since VRAM is the bottleneck.
    """
    import multiprocessing

    cpu_workers = (multiprocessing.cpu_count() * 2) + 1

    # Check if CUDA available (indicates GPU workload)
    try:
        import torch
        if torch.cuda.is_available():
            # Use conservative worker count for GPU apps
            # Runtime VRAM checking will prevent OOM
            # Fewer workers = less memory overhead, more predictable behavior
            gpu_conservative_workers = min(4, multiprocessing.cpu_count())
            return gpu_conservative_workers
    except ImportError:
        pass

    return cpu_workers
```

### Component 4: Runtime Status API

**Expose VRAM status through existing metadata endpoint:**

```python
# clams/app/__init__.py - Add method

def get_runtime_info(self) -> dict:
    """
    Get runtime information including GPU/VRAM status.
    Apps can override to add custom runtime info.
    """
    info = {}

    try:
        import torch
        if torch.cuda.is_available():
            devices = []
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                total = props.total_memory
                used = max(torch.cuda.memory_allocated(i),
                          torch.cuda.memory_reserved(i))

                devices.append({
                    'id': i,
                    'name': props.name,
                    'total_memory_gb': round(total / 1024**3, 2),
                    'available_memory_gb': round((total - used) / 1024**3, 2),
                })

            info['gpu'] = {'available': True, 'devices': devices}
    except:
        info['gpu'] = {'available': False}

    return info
```

```python
# clams/restify/__init__.py:121-129 - Modify GET handler

def get(self) -> Response:
    """Maps HTTP GET verb to appmetadata with optional runtime info"""
    raw_params = request.args.to_dict(flat=False)

    # Check for runtime info request
    if 'includeVRAM' in raw_params or 'includeRuntime' in raw_params:
        import json
        metadata = json.loads(self.cla.appmetadata(**raw_params))
        metadata['runtime'] = self.cla.get_runtime_info()
        return self.json_to_response(json.dumps(metadata))

    return self.json_to_response(self.cla.appmetadata(**raw_params))
```

**Usage:**
```bash
# Normal metadata
curl http://localhost:5000/

# Metadata + current VRAM status
curl http://localhost:5000/?includeVRAM=true
```

**Response example:**
```json
{
  "name": "Whisper Wrapper",
  "version": "1.0.0",
  "parameters": [...],
  "runtime": {
    "gpu": {
      "available": true,
      "devices": [
        {
          "id": 0,
          "name": "NVIDIA RTX 4090",
          "total_memory_gb": 24.0,
          "available_memory_gb": 18.5
        }
      ]
    }
  }
}
```

### Component 5: Automatic Memory Profiling

**When developers don't provide model requirements**, the SDK uses a conservative approach with historical profiling:

**Strategy:**
- **First request**: Require 80% of total VRAM to be available (very conservative)
- **Subsequent requests**: Use measured peak memory from previous runs (accurate)

**Persistence via hash-based filenames (write-once, read-many):**

```python
# clams/app/__init__.py - Add to ClamsApp

import hashlib
import json
import pathlib

class ClamsApp(ABC):

    def _get_param_hash(self, **parameters):
        """Create deterministic hash of parameters for filename"""
        param_str = json.dumps(parameters, sort_keys=True)
        return hashlib.sha256(param_str.encode()).hexdigest()[:16]

    def _get_profile_path(self, param_hash):
        """Get path for memory profile file"""
        cache_dir = pathlib.Path.home() / '.cache' / 'clams' / 'memory_profiles'
        return cache_dir / f"memory_{param_hash}.txt"

    def _get_model_requirements(self, **parameters):
        """
        Default implementation with conservative first request + historical profiling.
        Apps can override for explicit model size declarations.

        :param parameters: Runtime parameters from the request
        :return: Dict with 'size_bytes', 'name', and 'source'
        """
        param_hash = self._get_param_hash(**parameters)
        profile_path = self._get_profile_path(param_hash)

        # Check for historical measurement
        if profile_path.exists():
            try:
                measured = int(profile_path.read_text().strip())
                return {
                    'size_bytes': int(measured * 1.2),  # 20% buffer
                    'name': param_hash,
                    'source': 'historical'
                }
            except:
                pass  # Corrupted file, fall through to conservative

        # First request: require 80% of total VRAM
        try:
            import torch
            if torch.cuda.is_available():
                device = torch.cuda.current_device()
                total_vram = torch.cuda.get_device_properties(device).total_memory
                conservative_requirement = int(total_vram * 0.8)

                self.logger.info(
                    f"First request for {param_hash}: "
                    f"requiring 80% of VRAM ({conservative_requirement/1024**3:.2f}GB) "
                    f"until actual usage is measured"
                )

                return {
                    'size_bytes': conservative_requirement,
                    'name': param_hash,
                    'source': 'conservative-first-request'
                }
        except:
            pass

        return None

    def _record_memory_usage(self, parameters, peak_bytes):
        """
        Record peak memory to file using write-once pattern.
        Uses atomic write (temp file + rename) to avoid race conditions.

        :param parameters: Request parameters (used for hash)
        :param peak_bytes: Measured peak VRAM usage
        """
        param_hash = self._get_param_hash(**parameters)
        profile_path = self._get_profile_path(param_hash)

        try:
            profile_path.parent.mkdir(parents=True, exist_ok=True)

            # Only write if file doesn't exist or new measurement is higher
            should_write = True
            if profile_path.exists():
                try:
                    existing = int(profile_path.read_text().strip())
                    if peak_bytes <= existing:
                        should_write = False  # Existing value is fine
                    else:
                        self.logger.info(
                            f"Updating peak memory {param_hash}: "
                            f"{existing/1024**3:.2f}GB → {peak_bytes/1024**3:.2f}GB"
                        )
                except:
                    pass  # Corrupted, overwrite

            if should_write:
                # Atomic write: write to temp, then rename
                temp_path = profile_path.with_suffix('.tmp')
                temp_path.write_text(str(peak_bytes))
                temp_path.rename(profile_path)  # Atomic on POSIX

                self.logger.info(
                    f"Recorded peak memory for {param_hash}: {peak_bytes/1024**3:.2f}GB"
                )
        except Exception as e:
            self.logger.warning(f"Failed to record memory profile: {e}")
```

**File structure:**
```
~/.cache/clams/memory_profiles/
├── memory_3a7f2b9c.txt    # {model: "large", language: "en"} → "6442450944"
├── memory_8d2c1e4f.txt    # {model: "medium", language: "en"} → "3221225472"
└── memory_f1a9b3e7.txt    # {model: "large", language: "es"} → "6442450944"
```

**Race condition safety:**

| Scenario | Behavior | Outcome |
|----------|----------|---------|
| Two workers, same params, first request | Both write similar values | Last write wins, both valid |
| Worker reads while another writes | Atomic rename | Sees old or new file, never partial |
| Two workers update with higher values | Each reads, writes higher | Highest value persists |

**Benefits:**
- ✅ No developer effort required
- ✅ No file locking needed (write-once pattern)
- ✅ Atomic writes via temp + rename
- ✅ Shared across workers and restarts
- ✅ Self-calibrating over time
- ✅ Conservative first request prevents OOM

---

## How It Works

### Request Flow

1. **Client sends POST request** with MMIF data and parameters (e.g., `model=large`)

2. **SDK calls `_get_model_requirements()`** to determine memory needs
   - **If app overrides with explicit values**: Uses app-provided size (e.g., `6*1024**3`)
   - **If historical measurement exists**: Uses measured peak × 1.2 buffer
   - **If first request (no history)**: Requires 80% of total VRAM (conservative)

3. **SDK checks current VRAM availability**
   - Queries CUDA driver for real-time memory state
   - Accounts for memory used by other processes
   - Compares available vs. required (with 10% safety margin)

4. **Decision:**
   - **Sufficient VRAM**: Proceed to `_annotate()`, app loads model
   - **Insufficient VRAM**: Raise `RuntimeError`, return HTTP 500 with clear message

5. **After annotation completes**:
   - SDK records peak memory usage to profile file (for future requests)
   - SDK calls `torch.cuda.empty_cache()` to release cached memory

### Memory Requirement Resolution

```
Priority order for _get_model_requirements():

1. App override (explicit)     → App knows exact model sizes
2. Historical measurement      → Measured from previous run
3. Conservative 80%            → First request, no data yet
```

**Example progression for new parameter combination:**

| Request | Source | Requirement | Behavior |
|---------|--------|-------------|----------|
| 1st | conservative | 19.2GB (80% of 24GB) | Fails if <19.2GB available |
| 2nd+ | historical | 3.6GB (3GB measured × 1.2) | Accurate, efficient |

### Error Handling

**When VRAM is insufficient:**

```
HTTP 500 Internal Server Error

{
  "error": "Insufficient GPU memory for large. Required: 6.00GB, Available: 4.50GB. GPU may be in use by other processes. Please retry later."
}
```

**Client retry logic:**
```python
import requests
import time

def transcribe_with_retry(url, data, max_retries=3):
    for attempt in range(max_retries):
        response = requests.post(url, data=data)

        if response.ok:
            return response.json()

        if "Insufficient GPU memory" in response.text:
            wait = 5 * (2 ** attempt)  # Exponential backoff
            print(f"GPU busy, retrying in {wait}s...")
            time.sleep(wait)
            continue

        raise Exception(f"Request failed: {response.status_code}")

    raise Exception("Max retries exceeded")
```

---

## Benefits

### ✅ Centralized Solution
- All CLAMS apps benefit from VRAM management
- No need for each app to implement separately
- Consistent behavior across ecosystem

### ✅ Handles Dynamic VRAM
- Checks availability at request time
- Accounts for other processes using GPU
- No static assumptions about available memory

### ✅ Backward Compatible
- Existing apps continue working without changes
- Apps without `_get_model_requirements()` skip VRAM checking
- No breaking changes to API

### ✅ Clear Error Messages
- Clients know exactly why request failed
- Can implement retry logic
- Better than cryptic CUDA OOM errors

### ✅ Observable
- `includeVRAM` parameter exposes current GPU state
- Monitoring systems can track VRAM usage
- Helps with capacity planning

### ✅ Process-Safe
- `torch.cuda.empty_cache()` only affects current process
- No interference with other workers or applications
- Each worker manages its own CUDA context

---

## App Migration Path

### Phase 1: SDK Update (No App Changes Required)
1. Update SDK with VRAM checking components
2. Conservative worker count for CUDA-enabled systems
3. All apps automatically get `empty_cache()` cleanup
4. Runtime status available via `?includeVRAM=true`

### Phase 2: App Opt-In (Enhanced Behavior)
Apps implement `_get_model_requirements()`:

```python
class MyApp(ClamsApp):
    def _get_model_requirements(self, **parameters):
        # Declare memory needs
        return {'size_bytes': 3 * 1024**3, 'name': 'my-model'}
```

Now the app gets:
- Runtime VRAM checking before model load
- Clear error messages when insufficient memory
- Automatic fail-fast behavior

### Phase 3: Optional Enhancements
Apps can add:
- Model size estimates in metadata
- Alternative suggestions when VRAM low
- Idle model unloading after timeout

---

## Verification Plan

### 1. VRAM Isolation Test
Verify `empty_cache()` doesn't affect other processes:

```bash
# Terminal 1: Start whisper-wrapper
python app.py --production

# Terminal 2: Start another GPU app (e.g., another CLAMS app)
python other_app.py --production

# Terminal 3: Monitor GPU
watch -n 1 nvidia-smi

# Send requests to both apps simultaneously
# Verify: Each process maintains independent VRAM, no interference
```

### 2. Dynamic VRAM Test
Verify runtime checking handles contention:

```python
# Start app with available VRAM
# Load large model in separate process to consume VRAM
# Send request to app → should fail with clear error
# Unload model in separate process
# Retry request → should succeed
```

### 3. Multi-Worker Test
Verify conservative worker count prevents overload:

```bash
# 8-core machine, CUDA available
# Start app → verify ≤4 workers (not 17)
# Send concurrent requests
# Monitor VRAM → verify total usage stays within limits
```

### 4. Backward Compatibility Test
Verify apps without `_get_model_requirements()` still work:

```python
# Use app that doesn't implement _get_model_requirements()
# Send requests → should process normally
# VRAM checking skipped, but cleanup still happens
```

---

## Implementation Checklist

**SDK Changes - Core VRAM Management:**
- [ ] Add `_get_model_requirements()` with default implementation (80% conservative + historical)
- [ ] Add `_get_param_hash()` for deterministic parameter hashing
- [ ] Add `_get_profile_path()` for profile file location
- [ ] Add `_record_memory_usage()` with atomic write pattern
- [ ] Add `_check_vram_available()` static method
- [ ] Add `_get_available_vram()` static method
- [ ] Enhance `_profile_cuda_memory()` decorator with VRAM checking and recording

**SDK Changes - Configuration:**
- [ ] Modify `number_of_workers()` for conservative GPU count
- [ ] Add `get_runtime_info()` method to `ClamsApp`
- [ ] Modify `ClamsHTTPApi.get()` to support `includeVRAM` parameter

**Documentation:**
- [ ] Document automatic memory profiling behavior
- [ ] Document `_get_model_requirements()` override for explicit values
- [ ] Document `?includeVRAM=true` parameter for clients
- [ ] Document error handling and retry best practices
- [ ] Document profile file location and cleanup

**Testing:**
- [ ] Unit tests for VRAM checking logic
- [ ] Unit tests for hash-based file persistence
- [ ] Tests for atomic write behavior
- [ ] Integration tests with mock CUDA
- [ ] Multi-process isolation verification
- [ ] Backward compatibility tests

**App Updates (Optional - for explicit model sizes):**
- [ ] Update whisper-wrapper to override `_get_model_requirements()` with explicit sizes
- [ ] Update other GPU-based apps as needed

---

## Open Questions

1. **Profile File Location**: Is `~/.cache/clams/memory_profiles/` appropriate for all deployment scenarios? Consider container environments with ephemeral storage.

2. **Multi-GPU**: Should SDK support GPU selection/load balancing across devices?

3. **Health Endpoint**: Add dedicated `/health` endpoint in addition to `?includeVRAM`?

4. **Profile Cleanup**: Should SDK provide mechanism to clear old/stale profile files?

5. **Conservative Threshold**: Is 80% appropriate for first request, or should it be configurable?

---

## References

**Related Code:**
- `clams/app/__init__.py:349-392` - CUDA profiling decorator
- `clams/restify/__init__.py:42-78` - Production server setup
- `app-whisper-wrapper/app.py` - Real-world example with attempted mitigation

**Related Issues:**
- Issue #243: Main issue tracking this problem
- app-doctr-wrapper PR #6: Similar problem in different app

**External Resources:**
- [PyTorch CUDA Semantics](https://pytorch.org/docs/stable/notes/cuda.html)
- [Gunicorn Settings](https://docs.gunicorn.org/en/stable/settings.html)
- [CUDA Memory Management](https://developer.nvidia.com/blog/unified-memory-cuda-beginners/)

---

## Conclusion

The proposed SDK-level solution addresses the root cause of issue #243 by:

1. **Checking VRAM at runtime** - No static assumptions about availability
2. **Automatic memory profiling** - Conservative first request (80%), then uses measured values
3. **Zero developer effort** - Works without app changes; apps can optionally override for explicit values
4. **Race-condition safe persistence** - Hash-based files with atomic writes
5. **Failing fast with clear errors** - Better than OOM crashes
6. **Conservative worker defaults** - Prevents overloading GPU systems
7. **Centralized implementation** - All apps benefit automatically

This approach provides a robust foundation for GPU resource management in the CLAMS ecosystem while requiring no changes from app developers. Apps that want more precise control can override `_get_model_requirements()` with explicit model sizes.
