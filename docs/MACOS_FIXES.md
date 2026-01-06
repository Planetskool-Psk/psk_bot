# macOS Compatibility Fixes

This document describes the fixes applied to resolve segmentation faults on macOS ARM64 (Apple Silicon).

## Problem

The application was crashing with `SIGSEGV` (segmentation fault) errors on macOS due to:
1. **OpenMP library conflicts**: Multiple OpenMP instances (libomp.dylib) loaded by different libraries
2. **PyTorch threading issues**: Layer normalization operations failing in worker threads
3. **Multiprocessing conflicts**: Resource tracker warnings about leaked semaphores

## Root Cause

The crash occurred in `libtorch_cpu.dylib` during tensor operations, specifically:
- Thread 2 crashed in `__kmp_suspend_64` (OpenMP suspend function)
- During `torch::autograd::VariableType::native_layer_norm` operation
- Caused by invalid memory access at address `0x0000000000000008`

## Solutions Applied

### 1. Environment Variables (.env)

Added Mac-specific threading and compatibility settings:

```bash
# Disable PyTorch internal threading to prevent OpenMP conflicts
PYTORCH_ENABLE_MPS_FALLBACK=1
OMP_WAIT_POLICY=PASSIVE
KMP_BLOCKTIME=0

# Prevent multiprocessing issues on Mac
KMP_DUPLICATE_LIB_OK=TRUE
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Force single-threaded execution
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
VECLIB_MAXIMUM_THREADS=1
```

**Why this works:**
- `KMP_DUPLICATE_LIB_OK=TRUE`: Allows multiple OpenMP libraries without errors
- `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`: Prevents Objective-C runtime conflicts
- `OMP_WAIT_POLICY=PASSIVE`: Reduces thread spinning, avoiding race conditions
- `KMP_BLOCKTIME=0`: Threads don't block waiting for work
- All thread counts = 1: Forces single-threaded execution

### 2. Code Changes (vector_store.py)

Explicitly disabled PyTorch threading in the embedding model initialization:

```python
def _get_embedding_model(self) -> SentenceTransformer:
    if self._embedding_model is None:
        # Disable all threading to prevent OpenMP conflicts on Mac
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        
        self._embedding_model = SentenceTransformer(
            self._config.embedding_model_name,
            device="cpu",
            trust_remote_code=True,
        )
        logger.info("Embedding model loaded in full precision with threading disabled")
    return self._embedding_model
```

**Why this works:**
- `torch.set_num_threads(1)`: Disables intra-op parallelism
- `torch.set_num_interop_threads(1)`: Disables inter-op parallelism
- `device="cpu"`: Forces CPU execution (avoids MPS backend issues)
- `convert_to_numpy=True` in encode calls: Prevents tensor backend conflicts

### 3. WebSocket Handler Fix (events.py)

Fixed Flask-SocketIO disconnect handler signature:

```python
@socketio.on("disconnect")
def handle_disconnect(*args) -> None:  # Accept optional disconnect reason
    session_id = request.sid
    # ... rest of handler
```

**Why this works:**
- Flask-SocketIO 5.5.1 passes disconnect reason as argument
- Using `*args` makes handler compatible with both old and new versions

## Embedding Model Compatibility

### Tested Models

| Model | Status | Notes |
|-------|--------|-------|
| `all-MiniLM-L6-v2` | ✅ Works | Stable, recommended for Mac |
| `nomic-ai/nomic-embed-text-v1.5` | ⚠️ Unstable | Segfaults despite fixes, not recommended |

### Why nomic-ai Model Failed

Even with all threading fixes:
- Requires `trust_remote_code=True` and `einops` dependency
- Uses advanced tensor operations that conflict with Mac's Accelerate framework
- Half-precision conversion causes immediate crashes
- Better to use simpler, more stable models on Mac

## Performance Impact

Single-threaded execution results in:
- **Embedding generation**: ~3-4 seconds (vs. ~1-2s multi-threaded)
- **Query processing**: ~0.3s for vector search (acceptable)
- **Overall RAG response**: ~9s (mostly LLM generation time)

Trade-off is acceptable for development on Mac. For production, use Linux with proper multi-threading.

## Verification

Application now runs successfully:
- ✅ No segmentation faults
- ✅ 299 documents loaded in vector store
- ✅ RAG queries processing correctly
- ✅ WebSocket connections stable

## Future Recommendations

1. **For Development**: Continue using `all-MiniLM-L6-v2` on Mac
2. **For Production**: Deploy to Linux with multi-threading enabled
3. **Alternative**: Use Docker on Mac to isolate OpenMP dependencies
4. **Monitoring**: Watch for resource tracker warnings in logs

## Related Issues

- OpenMP library conflicts: Common on macOS due to multiple library sources
- Apple Silicon specific: ARM64 architecture has different threading behavior
- Accelerate framework: Apple's BLAS implementation conflicts with OpenBLAS/MKL

## References

- PyTorch threading: https://pytorch.org/docs/stable/notes/cpu_threading_torchscript_inference.html
- OpenMP on Mac: https://github.com/pytorch/pytorch/issues/78490
- Flask-SocketIO handlers: https://flask-socketio.readthedocs.io/en/latest/
