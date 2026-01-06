#!/usr/bin/env python3
"""Application entrypoint with optional optimizations for constrained environments."""

import gc
import os
import threading
import time
from typing import NoReturn

import eventlet
import psutil

# Configure worker-friendly defaults before importing heavy libraries
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "2")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

eventlet.monkey_patch()

from gentari_bot import create_app, socketio
from gentari_bot.logging import get_logger

logger = get_logger(__name__)
app = create_app()


def monitor_memory() -> NoReturn:
    """Emit warnings when memory pressure gets high."""
    while True:
        snapshot = psutil.virtual_memory()
        if snapshot.percent > 85:
            logger.warning(
                "High memory usage: %.1f%% (used %.2fGB / total %.2fGB)",
                snapshot.percent,
                snapshot.used / 1024**3,
                snapshot.total / 1024**3,
            )
            gc.collect()
        time.sleep(30)


def main() -> None:
    port = int(os.environ.get("PORT", "5173"))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    optimized = os.environ.get("OPTIMIZED_MODE", "false").lower() == "true"

    if optimized:
        # Start memory monitoring in optimized mode
        monitor = threading.Thread(target=monitor_memory, daemon=True)
        monitor.start()

        snapshot = psutil.virtual_memory()
        logger.info(
            "Starting optimized server on %s cores (RAM %.2fGB free %.2fGB)",
            psutil.cpu_count(),
            snapshot.total / 1024**3,
            snapshot.available / 1024**3,
        )
        eventlet.wsgi.HttpProtocol.default_request_version = "HTTP/1.0"
    else:
        logger.info("Starting Flask-SocketIO server on port %s (debug=%s)", port, debug)

    socketio.run(app, host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
