# Issue #243 Analysis: Gunicorn, Torch, and CUDA

## Executive Summary

When CLAMS applications using PyTorch models run in production mode with gunicorn, each worker process loads its own copy of the model into GPU VRAM. This leads to excessive memory consumption that scales linearly with the number of workers, causing OOM errors under concurrent load.

---

## The Problem in Detail

### Architecture

The CLAMS Python SDK uses gunicorn for production deployments:

```
clams/restify/__init__.py:42-78
```

**Default Configuration:**
- **Workers**: `(CPU_count × 2) + 1`
- **Threads per worker**: 2
- **Worker class**: sync (default)

On an 8-core machine: **17 workers**

### Root Cause

The issue occurs due to the interaction between:

1. **Python's fork model**: Gunicorn uses `os.fork()` to spawn workers
2. **CUDA memory allocation**: GPU memory is NOT shared via copy-on-write like CPU RAM
3. **Model loading timing**: Models are loaded in `ClamsApp.__init__()` before the fork

**Critical Code Path:**

```python
# Typical CLAMS app structure (clams/develop/templates/app/app.py.template:29-40)
class MyApp(ClamsApp):
    def __init__(self):
        super().__init__()
        self.model = torch.load('model.pt')  # ← Loaded BEFORE fork

# Entry point (clams/develop/templates/app/app.py.template:53-74)
if __name__ == "__main__":
    app = MyApp()  # ← Model loaded here (single process)
    http_app = Restifier(app, port=5000)

    if args.production:
        http_app.serve_production()  # ← Gunicorn forks 17 workers here
        # Each worker now has its own model copy in VRAM!
```

### Memory Multiplication

**Example with Whisper model (~3GB VRAM):**

| Configuration | Workers | VRAM Usage |
|--------------|---------|------------|
| 4-core CPU   | 9       | 27 GB      |
| 8-core CPU   | 17      | 51 GB      |
| 16-core CPU  | 33      | 99 GB      |

Most consumer GPUs have 8-24GB VRAM, so this quickly causes OOM errors.

### Why `torch.cuda.empty_cache()` Doesn't Help

The SDK includes CUDA cache cleanup (clams/app/__init__.py:389-390):

```python
finally:
    if torch_available and cuda_available:
        torch.cuda.empty_cache()
```

However, this only clears PyTorch's **caching allocator**, not the model weights themselves. The model stays loaded in each worker's VRAM indefinitely.

---

## Current Behavior vs. Expected Behavior

### Current (Problematic) Behavior:

1. App loads model in `__init__()`
2. Gunicorn forks N workers
3. Each worker has independent model in VRAM
4. Concurrent requests → N models active simultaneously
5. VRAM usage = N × model_size
6. OOM when N × model_size > available VRAM

### Expected Behavior:

Models should either:
1. **Load on-demand** per request and be freed after
2. **Share VRAM** across workers (if possible)
3. **Use a model server** pattern with worker pooling
4. **Limit workers** based on available VRAM, not CPU count

---

## How to Replicate and Test

### Test Script: `test_issue_243.py`

I've created a comprehensive test script that simulates the issue without requiring an actual whisper model.

#### Prerequisites

```bash
# Optional: For CUDA testing
pip install torch  # with CUDA support

# For monitoring mode
pip install requests
```

#### Test Scenarios

**1. Development Mode (Baseline)**
```bash
# Single process, single model in VRAM
python test_issue_243.py --mode dev --model-size 100
```

Expected: One model copy (~100MB VRAM)

**2. Production Mode (Demonstrates Issue)**
```bash
# Multiple workers, multiple models in VRAM
python test_issue_243.py --mode prod --model-size 100
```

Expected: N model copies (~N × 100MB VRAM)

**3. Concurrent Request Testing**

Terminal 1 - Start server:
```bash
python test_issue_243.py --mode prod --model-size 100 --port 5000
```

Terminal 2 - Send concurrent requests:
```bash
python test_issue_243.py --mode monitor --port 5000
```

**4. Custom Worker Count**
```bash
# Test with specific number of workers
python test_issue_243.py --mode prod --workers 5 --model-size 100
```

#### What to Look For

1. **Worker PIDs**: Each request shows which worker processed it
2. **VRAM Growth**: Monitor GPU memory as workers start
3. **Multiple Model Copies**: Different workers have different model instances
4. **Concurrent Load**: When 10 requests hit simultaneously, multiple workers activate

**With CUDA available:**
```bash
# Watch VRAM in real-time while running tests
watch -n 1 nvidia-smi
```

**Without CUDA:**
The script will simulate the issue and show worker-level model duplication even without GPU.

---

## Key Observations from Code Analysis

### 1. Worker Initialization (clams/restify/__init__.py:51-67)

```python
def number_of_workers():
    return (multiprocessing.cpu_count() * 2) + 1

class ProductionApplication(gunicorn.app.base.BaseApplication):
    def __init__(self, app, host, port, **options):
        self.options = {
            'bind': f'{host}:{port}',
            'workers': number_of_workers(),  # ← CPU-based, ignores GPU
            'threads': 2,
            'accesslog': '-',
        }
```

**Issue**: Worker count is based solely on CPU cores, completely ignoring GPU memory constraints.

### 2. CUDA Profiling (clams/app/__init__.py:349-392)

The SDK includes CUDA memory profiling that tracks peak VRAM usage:

```python
@staticmethod
def _profile_cuda_memory(func):
    def wrapper(*args, **kwargs):
        # Reset peak memory tracking
        torch.cuda.reset_peak_memory_stats('cuda')

        result = func(*args, **kwargs)

        # Record peak usage per GPU
        for device_id in range(device_count):
            peak_memory = torch.cuda.max_memory_allocated(f'cuda:{device_id}')
            cuda_profiler[key] = peak_memory

        return result, cuda_profiler
    finally:
        torch.cuda.empty_cache()  # ← Only clears cache, not model
```

**Key Points:**
- Profiling is helpful for monitoring
- `empty_cache()` doesn't free model weights
- Peak memory tracking is per-request, not per-worker

### 3. No Pre-Fork Hooks

Gunicorn provides hooks like `pre_fork()`, `post_fork()`, `post_worker_init()` that could be used to:
- Delay model loading until after fork
- Implement shared model serving
- Manage worker-to-GPU assignment

**Currently not implemented in the SDK.**

---

## Related Issues and Context

### Referenced PR: app-doctr-wrapper #6

The issue mentions this shares a root cause with a PR in app-doctr-wrapper. This suggests:
- Multiple CLAMS apps experience this issue
- DocTR (Document Text Recognition) models also consume significant VRAM
- The problem is systemic to the SDK, not app-specific

### Production Environment Context

The issue specifically mentions:
- **Hardware**: NVIDIA GPU support
- **App**: Whisper wrapper v10
- **Trigger**: Multiple POST requests (concurrent or sequential)
- **Symptom**: Progressive GPU memory saturation → OOM

This matches the behavior described above perfectly.

---

## Verification Steps

To verify this is happening in your production environment:

### 1. Check Worker Count
```bash
# While app is running in production
ps aux | grep gunicorn | grep -v grep | wc -l
```

You should see N+1 processes (master + N workers)

### 2. Monitor VRAM per Process
```bash
# Install nvidia-smi if not available
nvidia-smi pmon -c 1

# Or for continuous monitoring
watch -n 1 'nvidia-smi --query-compute-apps=pid,used_memory --format=csv'
```

You should see multiple PIDs each consuming ~model_size VRAM

### 3. Test Concurrent Requests

```python
import requests
from concurrent.futures import ThreadPoolExecutor

url = "http://your-app:5000"
mmif_data = "{}" # minimal MMIF

def send_request(i):
    response = requests.post(url, data=mmif_data,
                            params={'hwFetch': 'true'})
    return response.json()

# Send 10 concurrent requests
with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(send_request, range(10)))

# Check how many different workers responded
workers = set()
for result in results:
    if 'views' in result and result['views']:
        # Extract worker info from view metadata
        workers.add(result['views'][0].get('metadata', {}).get('app_pid'))

print(f"Requests distributed across {len(workers)} workers")
```

### 4. Compare Development vs. Production

```bash
# Development (single process)
python app.py --port 5000 &
sleep 5
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits

# Production (multiple workers)
python app.py --production --port 5001 &
sleep 10  # Give workers time to start
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
```

Production should show significantly more VRAM usage.

---

## Potential Solutions (Analysis Only)

*Note: Per your request, I'm only analyzing potential solutions, not implementing them.*

### 1. Lazy Model Loading
Load models in `_annotate()` instead of `__init__()`, with proper cleanup.

**Pros**: Simple to implement
**Cons**: Slow (load/unload per request), still uses same peak VRAM

### 2. Worker-to-GPU Affinity
Limit workers to match available GPUs, assign each worker to specific GPU.

**Pros**: Predictable VRAM usage
**Cons**: Underutilizes CPU on GPU-poor systems

### 3. Model Server Pattern
Separate model serving process(es), workers communicate via IPC/network.

**Pros**: True model sharing, scales independently
**Cons**: Complex architecture, adds latency

### 4. Gunicorn Pre-Load + Smart Fork
Use `preload_app=True` with delayed CUDA initialization after fork.

**Pros**: Maintains multi-worker concurrency
**Cons**: Requires careful CUDA context management

### 5. Dynamic Worker Scaling
Calculate workers based on available VRAM, not CPU count.

**Pros**: Prevents OOM
**Cons**: May underutilize system resources

---

## Recommended Next Steps

1. **Validate the issue** using `test_issue_243.py` on your setup
2. **Measure actual impact** in your production environment
3. **Gather requirements**:
   - Typical request concurrency
   - Model sizes
   - Available VRAM
   - Acceptable latency
4. **Evaluate solutions** based on your constraints
5. **Prototype** the most promising approach

---

## Additional Resources

### CLAMS SDK Files to Review:
- `clams/restify/__init__.py` - Gunicorn configuration
- `clams/app/__init__.py` - CUDA profiling and app lifecycle
- `clams/develop/templates/app/app.py.template` - App structure

### Gunicorn Documentation:
- [Server Hooks](https://docs.gunicorn.org/en/stable/settings.html#server-hooks)
- [Worker Configuration](https://docs.gunicorn.org/en/stable/settings.html#worker-processes)
- [Preloading Applications](https://docs.gunicorn.org/en/stable/settings.html#preload-app)

### PyTorch CUDA:
- [CUDA Semantics](https://pytorch.org/docs/stable/notes/cuda.html)
- [Memory Management](https://pytorch.org/docs/stable/notes/cuda.html#memory-management)
- [Multiprocessing](https://pytorch.org/docs/stable/notes/multiprocessing.html)

---

## Summary

Issue #243 is a **systemic architectural challenge** where the SDK's CPU-based worker scaling conflicts with GPU memory constraints. The test script (`test_issue_243.py`) provides a safe, controlled way to observe and measure this behavior without affecting your repository or production systems.

The issue is real, measurable, and impacts any CLAMS app using large PyTorch models in production. Solutions will require careful trade-offs between simplicity, performance, and resource utilization.
