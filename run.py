#!/usr/bin/env python3
"""Application entrypoint optimized for 2-core/12GB AMD Milan VM deployment."""

import gc
import os
import warnings

# Suppress Pydantic V1 compatibility warning for Python 3.14+
warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality isn't compatible")

from gevent import monkey
monkey.patch_all()

import threading
import time
from typing import NoReturn

import psutil

# ─── CPU/Memory tuning for 2-core AMD Milan VM ────────────────────────
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "2")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# FAISS optimizations for small core count
os.environ.setdefault("FAISS_DISABLE_GPU", "1")
os.environ.setdefault("FAISS_OPT_LEVEL", "avx2")  # AMD Milan supports AVX2

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
        logger.info("Optimized mode ON — tuned for 2-core/12GB VM")
        # Pre-warm: force garbage collection before serving
        gc.collect()

    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
