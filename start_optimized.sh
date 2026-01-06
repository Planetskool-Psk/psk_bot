#!/bin/bash
# Optimized startup script for 2-core, 8GB RAM VM

echo "🚀 Starting optimized chatbot for 2-core, 8GB RAM VM..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "🐍 Activating virtual environment..."
    source venv/bin/activate
fi

# Set system-level optimizations
export MALLOC_ARENA_MAX=2  # Limit memory arenas
export MALLOC_MMAP_THRESHOLD_=131072  # Use mmap for large allocations
export MALLOC_TRIM_THRESHOLD_=131072  # Trim threshold

# Python optimizations
export PYTHONOPTIMIZE=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1

# Enable optimized mode
export OPTIMIZED_MODE=true

# Threading optimizations for 2 cores (set to 1 for extra stability on Macs)
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}
export MKL_NUM_THREADS=${MKL_NUM_THREADS:-1}
export NUMEXPR_NUM_THREADS=${NUMEXPR_NUM_THREADS:-1}
export OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-1}
export VECLIB_MAXIMUM_THREADS=${VECLIB_MAXIMUM_THREADS:-1}
export TOKENIZERS_PARALLELISM=false
export FAISS_DISABLE_GPU=1
export PYTORCH_ENABLE_MPS_FALLBACK=1
export KMP_DUPLICATE_LIB_OK=TRUE

# Portable memory check (macOS/Linux)
MEM_INFO=$(python - <<'PY'
import os, sys
try:
    import psutil  # type: ignore
    vm = psutil.virtual_memory()
    print(f"{vm.total/1024/1024/1024:.1f}G {vm.available/1024/1024/1024:.1f}G")
except Exception:
    try:
        if sys.platform == "darwin":
            import subprocess, re
            total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
            vm_stat = subprocess.check_output(["vm_stat"]).decode()
            free_pages = 0
            for line in vm_stat.splitlines():
                if "free" in line.lower():
                    free_pages = int(re.findall(r"\\d+", line)[0])
                    break
            page_size = int(subprocess.check_output(["sysctl", "-n", "hw.pagesize"]).strip())
            avail = free_pages * page_size
            print(f"{total/1024/1024/1024:.1f}G {avail/1024/1024/1024:.1f}G")
        else:
            raise
    except Exception:
        print("unknown unknown")
PY
)
TOTAL_MEM=$(echo "$MEM_INFO" | awk '{print $1}')
AVAIL_MEM=$(echo "$MEM_INFO" | awk '{print $2}')
echo "💾 Total RAM: $TOTAL_MEM, Available: $AVAIL_MEM"

# Portable CPU core check
CPU_CORES=$(python - <<'PY'
import os
print(os.cpu_count() or 1)
PY
)
echo "🔧 CPU Cores: $CPU_CORES"

if [ "$CPU_CORES" -ne 2 ]; then
    echo "⚠️  Warning: Optimized for 2 cores, detected $CPU_CORES cores"
fi

# Start the application with memory monitoring
echo "🎯 Launching optimized chatbot..."
python3 run.py
