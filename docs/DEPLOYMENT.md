# Deployment Guide

## Docker Deployment

### Standard Mode
```bash
docker build -t gentari-chatbot .
docker run -d \
  --name gentari-chatbot \
  -p 5173:5173 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/vector_store:/app/vector_store \
  gentari-chatbot
```

### Optimized Mode (for 2-core, 8GB RAM VMs)
```bash
docker run -d \
  --name gentari-chatbot \
  -p 5173:5173 \
  --memory=6g \
  --cpus=2 \
  -e OPTIMIZED_MODE=true \
  -e OMP_NUM_THREADS=2 \
  -e MKL_NUM_THREADS=2 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/vector_store:/app/vector_store \
  gentari-chatbot
```

### Docker Compose
```yaml
version: '3.8'
services:
  chatbot:
    build: .
    ports:
      - "5173:5173"
    volumes:
      - ./data:/app/data
      - ./vector_store:/app/vector_store
    environment:
      - OPTIMIZED_MODE=true
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
    deploy:
      resources:
        limits:
          memory: 6G
          cpus: '2'
```

## Production Deployment with Gunicorn

```bash
gunicorn run:app \
  -k eventlet \
  -b 0.0.0.0:5173 \
  --timeout 120 \
  --workers 1 \
  --log-level info
```

## Environment Variables for Production

```bash
export DEBUG=false
export PORT=5173
export OPTIMIZED_MODE=true
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=gemma3:1b
```
