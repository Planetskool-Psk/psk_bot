#!/usr/bin/env python3
"""Cross-platform application entrypoint for PSK Bot.

Works on Windows, macOS, and Linux.
- Unix production: gunicorn + gevent
- Windows production: waitress
- Development: Flask built-in server (all platforms)
"""

import gc
import os
import platform
import sys
import warnings

# Suppress Pydantic V1 compatibility warning for Python 3.14+
warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality isn't compatible")

# gevent monkey-patching is only needed (and only works reliably) on Unix
_IS_WINDOWS = sys.platform == "win32"
if not _IS_WINDOWS:
    try:
        from gevent import monkey
        monkey.patch_all()
    except ImportError:
        pass  # gevent not installed — Flask dev server will be used

import threading
import time
from typing import NoReturn

import psutil

# ─── CPU/Memory tuning (cross-platform) ───────────────────────────────
_cpu = os.cpu_count() or 2
_threads = str(max(min(_cpu, 4), 1))  # cap at 4 threads, minimum 1

os.environ.setdefault("OMP_NUM_THREADS", _threads)
os.environ.setdefault("MKL_NUM_THREADS", _threads)
os.environ.setdefault("NUMEXPR_NUM_THREADS", _threads)
os.environ.setdefault("OPENBLAS_NUM_THREADS", _threads)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# macOS-only: Apple vecLib BLAS setting
if platform.system() == "Darwin":
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", _threads)

# FAISS optimizations
os.environ.setdefault("FAISS_DISABLE_GPU", "1")

from psk_bot import create_app
from psk_bot.logging import get_logger

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
    optimized = os.environ.get("OPTIMIZED_MODE", "true").lower() == "true"

    # Always start memory monitoring on servers
    monitor = threading.Thread(target=monitor_memory, daemon=True)
    monitor.start()

    snapshot = psutil.virtual_memory()
    cpu_count = psutil.cpu_count(logical=True)
    logger.info(
        "PSK Bot starting — %s cores, RAM %.2fGB free %.2fGB, port %s",
        cpu_count,
        snapshot.total / 1024**3,
        snapshot.available / 1024**3,
        port,
    )

    if optimized:
        logger.info("Optimized mode ON")
        # Pre-warm: force garbage collection before serving
        gc.collect()

    if _IS_WINDOWS:
        # gunicorn is Unix-only; use waitress on Windows
        try:
            from waitress import serve
            logger.info("Starting with Waitress (Windows production server)")
            serve(app, host="0.0.0.0", port=port)
        except ImportError:
            logger.warning("waitress not installed — falling back to Flask dev server")
            app.run(host="0.0.0.0", port=port, debug=debug)
    else:
        app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
