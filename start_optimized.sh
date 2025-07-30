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

# Threading optimizations for 2 cores
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2
export NUMEXPR_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
export VECLIB_MAXIMUM_THREADS=2
export TOKENIZERS_PARALLELISM=false

# Check if .env.optimized exists, copy it to .env
if [ -f ".env.optimized" ]; then
    echo "📋 Using optimized environment configuration..."
    cp .env.optimized .env
fi

# Check available memory
TOTAL_MEM=$(free -h | grep '^Mem:' | awk '{print $2}')
AVAIL_MEM=$(free -h | grep '^Mem:' | awk '{print $7}')
echo "💾 Total RAM: $TOTAL_MEM, Available: $AVAIL_MEM"

# Check CPU cores
CPU_CORES=$(nproc)
echo "🔧 CPU Cores: $CPU_CORES"

if [ $CPU_CORES -ne 2 ]; then
    echo "⚠️  Warning: Optimized for 2 cores, detected $CPU_CORES cores"
fi

# Start the application with memory monitoring
echo "🎯 Launching optimized chatbot..."
python3 run_optimized.py
