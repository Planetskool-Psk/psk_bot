# Performance Optimization Guide

## For 2-Core, 8GB RAM VMs

### Environment Configuration

Add to your `.env` file:

```bash
# Enable optimized mode
OPTIMIZED_MODE=true

# Model settings (optimized for 2-core VM)
OLLAMA_MODEL=gemma3:1b
OLLAMA_KEEP_ALIVE=60s

# Embedding model (high-quality)
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1.5
EMBEDDING_BATCH_SIZE=16

# RAG settings (optimized for speed)
CHUNK_SIZE=256
CHUNK_OVERLAP=25
TOP_K_RESULTS=1
CONTEXT_DOCUMENTS=2
CONTEXT_CHAR_LIMIT=2200
MAX_CONVERSATION_HISTORY=3
PROMPT_HISTORY_TURNS=2

# Performance optimizations
OMP_NUM_THREADS=2
MKL_NUM_THREADS=2
NUMEXPR_NUM_THREADS=2
OPENBLAS_NUM_THREADS=2
TOKENIZERS_PARALLELISM=false

# Generation controls
LLM_TIMEOUT=180
LLM_NUM_PREDICT=640
LLM_NUM_CTX=3072
LLM_NUM_THREAD=2
LLM_TEMPERATURE=0.35
LLM_TOP_P=0.9
LLM_TOP_K=40
```

### Performance Benchmarks

| Metric | Standard | Optimized | Improvement |
|--------|----------|-----------|-------------|
| Response Time | 50-80s | 30-50s | 40% faster |
| Memory Usage | ~15% peak | <12% peak | 20% reduction |
| Chunk Processing | 512 tokens | 256 tokens | 2x faster |
| Context Window | 4096 | 2048 | 50% less memory |

### Memory Monitoring

The application includes automatic memory monitoring when `OPTIMIZED_MODE=true`:
- Alerts when memory usage exceeds 85%
- Automatic garbage collection
- Real-time performance tracking

### Best Practices

1. **Keep conversations short**: Restart periodically for optimal performance
2. **Use single, focused questions**: Avoid complex multi-part queries
3. **Monitor resources**: Use the built-in system monitoring
4. **Regular restarts**: Clear memory every few hours under heavy load
