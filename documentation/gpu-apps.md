## GPU Memory Management for CLAMS Apps

This document covers GPU memory management features in the CLAMS SDK for developers building CUDA-based applications.

### Overview

CLAMS apps that use GPU acceleration face memory management challenges when running as HTTP servers with multiple workers. Each gunicorn worker loads models independently into GPU VRAM, which can cause out-of-memory (OOM) errors.

> **Note**: The VRAM profiling and runtime checking features described in this document are **PyTorch-only**. Apps using TensorFlow or other frameworks will not benefit from automatic VRAM profiling, though worker calculation based on `gpu_mem_min` still works. TensorFlow-based apps should set conservative `gpu_mem_min` values and rely on manual testing to determine appropriate worker counts.

The CLAMS SDK provides:
1. **Metadata fields** for declaring GPU memory requirements
2. **Automatic worker scaling** based on available VRAM
3. **Runtime VRAM checking** to reject requests when memory is insufficient
4. **Memory profiling** to optimize future requests

### Declaring GPU Memory Requirements

App developers should declare GPU memory requirements in the app metadata using two fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `gpu_mem_min` | int | 0 | Minimum GPU memory required to run the app (MB) |
| `gpu_mem_typ` | int | 0 | Typical GPU memory usage with default parameters (MB) |

#### Example

```python
from clams.app import ClamsApp
from clams.appmetadata import AppMetadata

class MyGPUApp(ClamsApp):
    def _appmetadata(self):
        metadata = AppMetadata(
            name="My GPU App",
            description="An app that uses GPU acceleration",
            app_license="MIT",
            identifier="my-gpu-app",
            url="https://example.com/my-gpu-app",
            gpu_mem_min=4000,  # 4GB minimum
            gpu_mem_typ=6000,  # 6GB typical usage
        )
        # ... add inputs/outputs/parameters
        return metadata
```

#### Guidelines for Setting Values

- **`gpu_mem_min`**: The absolute minimum VRAM needed to load the smallest supported model configuration. 0 (the default) means the app does not use GPU.

- **`gpu_mem_typ`**: Expected VRAM usage with default parameters. This value is displayed to users and helps them understand resource requirements. Must be >= `gpu_mem_min`.

If `gpu_mem_typ` is set lower than `gpu_mem_min`, the SDK will automatically correct it and issue a warning.

### Automatic Worker Calculation

When running in production mode (gunicorn), the SDK automatically calculates the optimal number of workers based on:

1. CPU cores: `(cores × 2) + 1`
2. Available VRAM: `total_vram / gpu_mem_min`

The final worker count is the minimum of these two values, ensuring workers don't exceed available GPU memory.

#### Example Calculation

For a system with:
- 8 CPU cores → 17 CPU-based workers
- 24GB VRAM, app requires 4GB → 6 VRAM-based workers

Result: 6 workers (limited by VRAM)

#### Overriding Worker Count

Use the `CLAMS_WORKERS` environment variable to override automatic calculation:

```bash
# Set fixed number of workers
CLAMS_WORKERS=2 python app.py --production

# In Docker
docker run -e CLAMS_WORKERS=2 -p 5000:5000 <IMAGE_NAME>
```

### Runtime VRAM Checking

Beyond worker calculation, the SDK performs runtime VRAM checks before each annotation request. This catches cases where:
- Other processes are using GPU memory
- Previous requests haven't fully released memory
- Memory fragmentation reduces effective available space

#### How It Works

1. **Before annotation**: The SDK estimates required VRAM based on:
   - Historical measurements from previous runs (with 20% buffer)
   - Conservative estimate (80% of total VRAM) for first request

2. **If insufficient VRAM**: The request is rejected with `InsufficientVRAMError`

3. **After annotation**: Peak memory usage is recorded for future estimates

#### HTTP Response

When VRAM is insufficient, the REST API returns:
- **Status**: 503 Service Unavailable
- **Body**: Error message describing the shortage

This allows clients to implement retry logic with backoff.

### Memory Profiling

The SDK automatically profiles and caches memory usage per parameter combination.

#### Profile Storage

Profiles are stored in:
```
~/.cache/clams/memory_profiles/<app_id>/<param_hash>.txt
```

Each profile contains a single integer: the peak memory usage in bytes.

#### Profile Behavior

- **First request**: Uses conservative estimate (80% of total VRAM)
- **Subsequent requests**: Uses historical measurement × 1.2 buffer
- **Updates**: Only when new peak exceeds stored value

This approach becomes more accurate over time while maintaining safety margins.

### Error Handling

#### InsufficientVRAMError

A custom exception raised when VRAM is insufficient:

```python
from clams.app import InsufficientVRAMError

try:
    result = app.annotate(mmif_input)
except InsufficientVRAMError as e:
    # Handle insufficient memory
    print(f"Not enough GPU memory: {e}")
```

This exception inherits from `RuntimeError` for backward compatibility.

#### Best Practices

1. **Catch the exception** in custom code that calls `annotate()` directly
2. **Implement retry logic** when receiving HTTP 503
3. **Monitor memory usage** using the `hwFetch` parameter

### Monitoring with hwFetch

Enable hardware information in responses to monitor GPU usage:

```bash
# Via HTTP query parameter
curl -X POST "http://localhost:5000/?hwFetch=true" -d@input.mmif

# Via CLI
python cli.py --hwFetch true input.mmif output.mmif
```

Response metadata will include:
```json
{
  "app-metadata": {
    "hwFetch": "NVIDIA RTX 4090, 20480 MB available, 3584 MB peak used"
  }
}
```

### Conditions for VRAM Checking

VRAM checking is only performed when all conditions are met:

1. PyTorch is installed (`import torch` succeeds)
2. CUDA is available (`torch.cuda.is_available()` returns True)
3. App declares GPU requirements (`gpu_mem_min > 0`)

Apps without GPU requirements (default `gpu_mem_min=0`) skip all VRAM checks.

> **Important**: TensorFlow-based apps will not trigger VRAM checking even with `gpu_mem_min > 0`, because the profiling relies on PyTorch's CUDA APIs. For TensorFlow apps, the `gpu_mem_min` value is still used for worker calculation, but runtime VRAM checking and memory profiling are disabled.

### Memory Optimization Tips

1. **Clear cache between requests**: The SDK calls `torch.cuda.empty_cache()` after annotation

2. **Use appropriate batch sizes**: Smaller batches use less memory but may be slower

3. **Consider model variants**: Offer parameters for different model sizes (e.g., base/large/xl)

4. **Test on target hardware**: Memory usage varies by GPU architecture

5. **Set accurate metadata values**: Measure actual usage rather than guessing

### Migration Guide

To add GPU memory management to an existing app:

1. **Measure memory usage**: Run your app and note peak VRAM usage

2. **Update metadata**: Add `gpu_mem_min` and `gpu_mem_typ` fields

3. **Test worker scaling**: Run in production mode and verify worker count

4. **Test rejection logic**: Simulate low VRAM scenarios

5. **Update documentation**: Inform users of GPU requirements

### Troubleshooting

#### Workers not scaling correctly

- Verify `gpu_mem_min` is set in metadata (not 0)
- Check PyTorch is installed and CUDA is available
- Use `CLAMS_WORKERS` to override if needed

#### Requests being rejected unexpectedly

- Check available VRAM with `nvidia-smi`
- Clear GPU memory from other processes
- Profile cache may have outdated high values (delete `~/.cache/clams/memory_profiles/`)

#### OOM errors despite worker limits

- `gpu_mem_min` may be set too low
- Memory fragmentation; try restarting workers
- Other processes consuming VRAM

### API Reference

#### AppMetadata Fields

```python
gpu_mem_min: int = 0  # Minimum GPU memory (MB)
gpu_mem_typ: int = 0  # Typical GPU memory usage (MB)
```

#### Exception Classes

```python
class InsufficientVRAMError(RuntimeError):
    """Raised when insufficient GPU memory is available."""
    pass
```

#### Internal Methods

These methods are used internally but documented for reference:

- `ClamsApp._get_estimated_vram_usage(**params)` - Get estimated VRAM for parameters
- `ClamsApp._record_vram_usage(params, peak_bytes)` - Record peak usage
- `ClamsApp._check_vram_available(required_bytes)` - Check if VRAM sufficient
- `ClamsApp._get_available_vram()` - Get current available VRAM
