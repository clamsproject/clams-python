# Issue #243 Real-World Analysis: Whisper Wrapper Implementation

## Executive Summary

The whisper wrapper app **attempts** to solve the GPU memory issue by loading models on-demand rather than in `__init__()`. However, the implementation still suffers from **per-worker model duplication** and has a problematic **"conflict prevention" mechanism** that can load duplicate models within the same worker.

---

## Actual Implementation Analysis

### Source Code
**Repository**: https://github.com/clamsproject/app-whisper-wrapper
**File**: `app.py`

### Model Loading Strategy

#### 1. Initialization (Lines 28-31)
```python
def __init__(self):
    super().__init__()
    self.whisper_models = {}
    self.model_usage = {}
```

**Good**: Models are NOT loaded in `__init__()`, avoiding the pre-fork duplication issue.

**Problem**: Each worker still has its own `self.whisper_models` dict after fork, leading to per-worker caching.

#### 2. On-Demand Loading in `_annotate()` (Lines 78-96)

```python
if size not in self.whisper_models:
    self.logger.debug(f'Loading model {size}')
    t = time.perf_counter()
    self.whisper_models[size] = whisper.load_model(size)
    self.logger.debug(f'Load time: {time.perf_counter() - t:.2f} seconds\n')
    self.model_usage[size] = False

if not self.model_usage[size]:
    whisper_model = self.whisper_models.get(size)
    self.model_usage[size] = True
    cached = True
else:
    self.logger.debug(f'Loading model {size} to avoid memory conflict')
    t = time.perf_counter()
    whisper_model = whisper.load_model(size)
    self.logger.debug(f'Load time: {time.perf_counter() - t:.2f} seconds\n')
    cached = False
```

**Logic**:
1. First request to a worker: Load model into `self.whisper_models[size]` and cache it
2. Subsequent requests to the same worker:
   - If `model_usage[size]` is False (model not in use): Use cached model
   - If `model_usage[size]` is True (model in use): **Load a SECOND copy!**

#### 3. Cleanup After Transcription (Line 128)
```python
if size in self.model_usage and cached == True:
    self.model_usage[size] = False
```

**Intent**: Mark model as "not in use" so next request can reuse it.

**Problem**: The second model copy (when `cached = False`) is never tracked or cleaned up!

---

## Why This Is Still Problematic

### Issue #1: Per-Worker Model Caching

**Scenario**: 8-core CPU → 17 workers, Whisper "medium" model (~3GB VRAM)

**What happens**:
1. First request hits Worker 1 → loads model (3GB)
2. First request hits Worker 2 → loads model (3GB)
3. ...
4. First request hits Worker 17 → loads model (3GB)

**Result**: 17 × 3GB = **51GB VRAM** (same as the original issue!)

**Why**: Each worker's `self.whisper_models` dict is independent. There's no cross-worker model sharing.

### Issue #2: The "Conflict Prevention" Mechanism

The code assumes concurrent requests within the same worker can happen. Let's analyze when this occurs:

**Gunicorn Worker Types**:
- **sync** (default in CLAMS SDK): Single-threaded, handles one request at a time
  - The `threads: 2` setting is **ignored** with sync workers!
  - `model_usage` tracking is **unnecessary** with sync workers
- **gthread**: Multi-threaded, can handle concurrent requests
  - If using gthread workers, the conflict prevention kicks in

**Problem with gthread workers (2 threads per worker)**:

**Timeline**:
```
Worker 1, Thread 1:
  T0: Load model into cache (3GB)
  T1: Set model_usage = True
  T2: Start transcription (takes 10 seconds)

Worker 1, Thread 2 (concurrent request):
  T3: Check model_usage → True
  T4: "Loading model to avoid memory conflict"
  T5: Load SECOND copy of model (3GB)
  T6: Start transcription

Worker 1 now has: 3GB + 3GB = 6GB in VRAM!
```

**Worst Case**: 17 workers × 2 threads × 3GB = **102GB VRAM**

### Issue #3: Memory Leak

```python
else:
    self.logger.debug(f'Loading model {size} to avoid memory conflict')
    t = time.perf_counter()
    whisper_model = whisper.load_model(size)  # ← Local variable
    self.logger.debug(f'Load time: {time.perf_counter() - t:.2f} seconds\n')
    cached = False
```

**Problem**: The second model copy is stored in `whisper_model` (local variable) but never explicitly deleted or freed. It becomes garbage only when:
1. The function returns
2. Python's GC runs
3. PyTorch releases the CUDA memory

During long transcriptions, multiple copies can accumulate if requests arrive faster than transcription completes.

---

## Verification Steps

### Check If You're Hitting This Issue

**1. Check Worker Configuration**

Look at the actual running gunicorn config:
```bash
# While app is running
ps aux | grep gunicorn

# You'll see something like:
# gunicorn: master [WhisperWrapper]
# gunicorn: worker [WhisperWrapper] (17 workers)
```

Count the workers: should be `(CPU_count × 2) + 1`

**2. Monitor Per-Worker VRAM Usage**

```bash
# Watch VRAM in real-time
watch -n 1 'nvidia-smi --query-compute-apps=pid,used_memory --format=csv'
```

Send a request and watch:
- First request to the app → 1 PID appears with ~3GB
- Second concurrent request → potentially 2 PIDs or the same PID with 6GB

**3. Test Concurrent Requests**

```python
import requests
import time
from concurrent.futures import ThreadPoolExecutor
import json

url = "http://your-whisper-app:5000"

# Create minimal MMIF with audio document
mmif = {
    "metadata": {"mmif": "http://mmif.clams.ai/1.0.0"},
    "documents": [{
        "@type": "http://mmif.clams.ai/vocabulary/AudioDocument/v1",
        "properties": {
            "id": "d1",
            "location": "file:///path/to/audio.mp3"
        }
    }]
}

def send_request(i):
    start = time.time()
    response = requests.post(url, json=mmif, params={'model': 'medium'})
    duration = time.time() - start

    # Extract worker PID from logs if available
    print(f"Request {i}: {response.status_code}, took {duration:.2f}s")
    return response.json() if response.ok else None

# Send 5 concurrent requests
print("Sending concurrent requests...")
with ThreadPoolExecutor(max_workers=5) as executor:
    results = list(executor.map(send_request, range(5)))

print(f"\nCompleted {len([r for r in results if r])} successful requests")
```

Watch `nvidia-smi` while this runs. You should see:
- Multiple PIDs (different workers) each consuming ~3GB, OR
- Same PID consuming 6GB+ (multiple models in one worker)

---

## The Actual Problem Mechanism

### Scenario 1: Low Concurrency (< Workers)

**Setup**: 17 workers, 5 concurrent requests

**What happens**:
1. Request 1 → Worker 1 loads model (3GB)
2. Request 2 → Worker 2 loads model (3GB)
3. Request 3 → Worker 3 loads model (3GB)
4. Request 4 → Worker 4 loads model (3GB)
5. Request 5 → Worker 5 loads model (3GB)

**Total**: 5 × 3GB = 15GB VRAM

**After requests complete**: Models stay cached in workers 1-5

**Next 5 requests**: Might reuse cached models OR hit different workers and load 5 more

**Over time**: All 17 workers eventually load models → 51GB VRAM

### Scenario 2: High Concurrency (> Workers)

**Setup**: 17 workers, 50 concurrent requests

**What happens**:
1. Requests 1-17 → Each worker loads one model (51GB)
2. Requests 18-34 → Reuse cached models (no new VRAM)
3. **IF using gthread workers**: Some requests queue up, then hit "in use" models
   - Additional model copies loaded (potentially +51GB more!)

**Total**: 51GB to 102GB VRAM depending on timing

### Scenario 3: Varied Model Sizes

**Setup**: Requests use different model parameters ('small', 'medium', 'large')

**What happens**:
- Each worker caches ALL requested model sizes
- Worker 1: small (1GB) + medium (3GB) = 4GB
- Worker 2: medium (3GB) + large (6GB) = 9GB
- ...

**Total**: Unpredictable, can exceed single-model worst case

---

## Why the "Fix" Doesn't Work

The whisper wrapper's approach tries to handle:
1. ✅ Avoiding pre-fork model loading (works)
2. ✅ Lazy loading on first request (works)
3. ✅ Caching within a worker (works)
4. ❌ Concurrent requests within a worker (broken - loads duplicates)
5. ❌ Cross-worker model sharing (impossible with this architecture)

**The fundamental issue**: Python's multiprocessing fork + CUDA don't support shared GPU memory.

---

## Better Testing Strategy

### Modified Test Script for Whisper Wrapper

```python
#!/usr/bin/env python3
"""
Test script specifically for whisper-wrapper issue #243
"""
import requests
import time
import subprocess
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://localhost:5000"

def get_gpu_memory():
    """Get current GPU memory usage"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
            capture_output=True, text=True
        )
        return int(result.stdout.strip())
    except:
        return None

def get_gpu_processes():
    """Get PIDs using GPU and their memory"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'],
            capture_output=True, text=True
        )
        processes = {}
        for line in result.stdout.strip().split('\n'):
            if line:
                pid, mem = line.split(', ')
                processes[int(pid)] = int(mem)
        return processes
    except:
        return {}

def create_mmif_input(audio_path):
    """Create minimal MMIF with audio document"""
    return json.dumps({
        "metadata": {"mmif": "http://mmif.clams.ai/1.0.0"},
        "documents": [{
            "@type": "http://mmif.clams.ai/vocabulary/AudioDocument/v1",
            "properties": {
                "id": "d1",
                "location": f"file://{audio_path}"
            }
        }]
    })

def send_request(request_id, model_size='medium', audio_path='/path/to/test.mp3'):
    """Send transcription request"""
    mmif_input = create_mmif_input(audio_path)

    start = time.time()
    try:
        response = requests.post(
            BASE_URL,
            data=mmif_input,
            params={'model': model_size, 'hwFetch': 'true'},
            headers={'Content-Type': 'application/json'},
            timeout=300
        )
        duration = time.time() - start

        if response.ok:
            result = response.json()
            worker_info = "unknown"
            if 'views' in result and result['views']:
                metadata = result['views'][0].get('metadata', {})
                worker_info = metadata.get('worker_pid', 'unknown')

            return {
                'id': request_id,
                'status': 'success',
                'duration': duration,
                'worker': worker_info,
                'model': model_size
            }
        else:
            return {
                'id': request_id,
                'status': 'error',
                'error': response.status_code,
                'duration': duration
            }
    except Exception as e:
        return {
            'id': request_id,
            'status': 'exception',
            'error': str(e),
            'duration': time.time() - start
        }

def main():
    print("\n" + "="*70)
    print("WHISPER WRAPPER - Issue #243 Test")
    print("="*70)

    # Initial state
    print("\n1. Initial GPU State:")
    initial_mem = get_gpu_memory()
    initial_procs = get_gpu_processes()
    print(f"   Total VRAM used: {initial_mem} MB")
    print(f"   Processes using GPU: {len(initial_procs)}")

    # Test 1: Single request
    print("\n2. Sending single request...")
    result = send_request(1, model_size='medium', audio_path='/path/to/short-test.mp3')
    print(f"   Result: {result['status']}, Duration: {result['duration']:.2f}s")

    time.sleep(2)
    after_one_mem = get_gpu_memory()
    after_one_procs = get_gpu_processes()
    print(f"   VRAM after 1 request: {after_one_mem} MB (Δ {after_one_mem - initial_mem} MB)")
    print(f"   Processes: {len(after_one_procs)} - {after_one_procs}")

    # Test 2: Sequential requests (should reuse model in same worker)
    print("\n3. Sending 5 sequential requests...")
    for i in range(2, 7):
        result = send_request(i, model_size='medium')
        print(f"   Request {i}: {result['status']}, Worker: {result.get('worker', 'unknown')}")
        time.sleep(1)

    after_seq_mem = get_gpu_memory()
    after_seq_procs = get_gpu_processes()
    print(f"   VRAM after sequential: {after_seq_mem} MB (Δ {after_seq_mem - initial_mem} MB)")
    print(f"   Processes: {len(after_seq_procs)} - {after_seq_procs}")

    # Test 3: Concurrent requests (this will trigger multi-worker loading)
    print("\n4. Sending 10 concurrent requests...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(send_request, i, 'medium') for i in range(10, 20)]
        results = [f.result() for f in as_completed(futures)]

    workers_used = set(r.get('worker') for r in results if r.get('worker'))
    print(f"   Completed: {len([r for r in results if r['status'] == 'success'])}/10")
    print(f"   Unique workers: {len(workers_used)} - {workers_used}")

    time.sleep(2)
    after_concurrent_mem = get_gpu_memory()
    after_concurrent_procs = get_gpu_processes()
    print(f"   VRAM after concurrent: {after_concurrent_mem} MB (Δ {after_concurrent_mem - initial_mem} MB)")
    print(f"   Processes: {len(after_concurrent_procs)} - {after_concurrent_procs}")

    # Analysis
    print("\n" + "="*70)
    print("ANALYSIS:")
    print("="*70)
    print(f"Initial VRAM: {initial_mem} MB")
    print(f"After 1 request: {after_one_mem} MB (1 model loaded)")
    print(f"After sequential: {after_seq_mem} MB (should be same if worker reused)")
    print(f"After concurrent: {after_concurrent_mem} MB ({len(workers_used)} workers loaded models)")
    print(f"\nExpected VRAM per model: ~3000 MB (medium)")
    print(f"Expected for {len(workers_used)} workers: ~{len(workers_used) * 3000} MB")
    print(f"Actual increase: {after_concurrent_mem - initial_mem} MB")

    if len(workers_used) > 5:
        print(f"\n⚠️  WARNING: {len(workers_used)} different workers loaded models!")
        print(f"   This demonstrates the issue: each worker loads independently")

    if len(after_concurrent_procs) > len(workers_used):
        print(f"\n⚠️  WARNING: More GPU processes than unique workers!")
        print(f"   This suggests duplicate models within workers (conflict prevention)")

    print("="*70 + "\n")

if __name__ == '__main__':
    # NOTE: Update the audio_path in send_request() to point to a real audio file
    main()
```

**Usage**:
1. Start whisper-wrapper in production mode
2. Update `audio_path` in the script to point to a real audio file
3. Run the test script
4. Watch memory grow as concurrent requests hit different workers

---

## Summary

The whisper wrapper's implementation reveals:

1. **Models are NOT loaded in `__init__()`** - This is good and avoids one problem
2. **Models ARE cached per-worker** - Each worker loads its own copy on first use
3. **"Conflict prevention" loads duplicates** - If configured with threaded workers
4. **No cleanup mechanism** - Models stay in VRAM indefinitely per worker

**The core issue remains**: With 17 workers and a 3GB model, you still get 51GB VRAM usage over time as different workers handle requests.

This is **architectural** - the solution requires either:
- Limiting workers based on VRAM (not CPU)
- External model serving
- Different worker/threading strategy
- Or accepting high VRAM usage and scaling horizontally with multiple GPUs

---

## Recommended Next Steps

1. **Measure your actual VRAM usage** using the test script above
2. **Determine your concurrency needs** (how many concurrent requests?)
3. **Calculate required VRAM**: workers needed × model size
4. **Compare to available VRAM** on your GPU(s)
5. **Decide on solution approach** based on gap

The whisper wrapper attempts to mitigate the issue but can't solve it within the current architecture.
