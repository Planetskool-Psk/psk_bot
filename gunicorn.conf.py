# ═══════════════════════════════════════════════════════════════════════
# PSK Bot — Gunicorn Configuration
# Target: 2-core, 12GB RAM, AMD Milan VM
# ═══════════════════════════════════════════════════════════════════════

import multiprocessing
import os

# ─── Server socket ────────────────────────────────────────────────────
bind = f"0.0.0.0:{os.getenv('PORT', '5173')}"
backlog = 64

# ─── Worker configuration ────────────────────────────────────────────
# For 2-core VM: 1 worker (gevent handles concurrency via greenlets)
# Multiple workers would duplicate the model in memory
workers = 1
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
worker_connections = 100
timeout = 120
keepalive = 5

# ─── Resource limits ─────────────────────────────────────────────────
max_requests = 1000  # Recycle workers to prevent memory leaks
max_requests_jitter = 100
graceful_timeout = 30

# ─── Logging ─────────────────────────────────────────────────────────
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" %(D)sμs'

# ─── Process naming ──────────────────────────────────────────────────
proc_name = "psk-bot"

# ─── Pre/post hooks ──────────────────────────────────────────────────
def on_starting(server):
    """Pre-warm: ensure Ollama model is loaded."""
    import subprocess
    try:
        subprocess.run(
            ["ollama", "run", "gemma3:1b", "hi"],
            capture_output=True,
            timeout=60,
        )
        server.log.info("Pre-warmed gemma3:1b model")
    except Exception as e:
        server.log.warning(f"Model pre-warm failed: {e}")


def post_fork(server, worker):
    """Set CPU affinity after fork if possible."""
    import gc
    gc.collect()
