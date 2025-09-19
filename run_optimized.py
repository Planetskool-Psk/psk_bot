#!/usr/bin/env python3
"""
Optimized startup script for 2-core, 8GB RAM VM
This script includes memory optimizations and monitoring
"""

import os
import gc
import psutil
import threading
import time
from functools import wraps

# Set memory optimizations before importing heavy libraries
os.environ['OMP_NUM_THREADS'] = '2'  # Match your VM cores
os.environ['MKL_NUM_THREADS'] = '2'  # Intel Math Kernel Library
os.environ['NUMEXPR_NUM_THREADS'] = '2'  # NumExpr
os.environ['OPENBLAS_NUM_THREADS'] = '2'  # OpenBLAS
os.environ['VECLIB_MAXIMUM_THREADS'] = '2'  # Apple Accelerate
os.environ['TOKENIZERS_PARALLELISM'] = 'false'  # Disable tokenizer parallelism warnings

# Memory monitoring
def monitor_memory():
    """Background memory monitoring"""
    while True:
        memory = psutil.virtual_memory()
        if memory.percent > 85:  # Alert if memory usage > 85%
            print(f"⚠️  High memory usage: {memory.percent:.1f}% ({memory.used/1024**3:.2f}GB/{memory.total/1024**3:.2f}GB)")
            gc.collect()  # Force garbage collection
        time.sleep(30)  # Check every 30 seconds

# Start memory monitor in background
memory_thread = threading.Thread(target=monitor_memory, daemon=True)
memory_thread.start()

# Import heavy libraries after setting environment
import eventlet
eventlet.monkey_patch()
from app import create_app, socketio
from utils.logger import log

app = create_app()

def main() -> None:
    port = int(os.environ.get("PORT", 5173))
    debug = os.environ.get("DEBUG", "False").lower() == "true"
    
    # Log system info
    memory = psutil.virtual_memory()
    cpu_count = psutil.cpu_count()
    log.info(f"🚀 Starting optimized Flask-SocketIO server on {cpu_count}-core VM")
    log.info(f"💾 Available RAM: {memory.total/1024**3:.2f}GB (Free: {memory.available/1024**3:.2f}GB)")
    log.info(f"🔧 Memory monitoring enabled - alerts at >85% usage")
    log.info(f"🤖 Embedding model (all-MiniLM-L6-v2) will be preloaded during startup...")
    
    # Configure eventlet for lower memory usage
    eventlet.wsgi.HttpProtocol.default_request_version = "HTTP/1.0"
    
    # Run with optimized settings for 2-core VM
    socketio.run(
        app, 
        host="0.0.0.0", 
        port=port, 
        debug=debug
    )

if __name__ == "__main__":
    main()
