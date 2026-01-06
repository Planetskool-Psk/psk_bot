#!/bin/bash
# Quick setup script for optimized chatbot

echo "🔧 Setting up optimized chatbot for 2-core, 8GB RAM VM..."

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "🐍 Python version: $PYTHON_VERSION"

# Install psutil if not present (for monitoring)
python3 -c "import psutil" 2>/dev/null || {
    echo "📦 Installing psutil for system monitoring..."
    pip3 install psutil
}

# Backup current .env if it exists
if [ -f ".env" ]; then
    echo "💾 Backing up current .env to .env.backup"
    cp .env .env.backup
fi

echo ""
echo "✅ Setup complete! You can now run:"
echo "   ./start_optimized.sh    # Start the optimized chatbot"
echo "   python3 monitor_system.py    # Monitor system performance"
echo ""
echo "💡 Optimizations applied:"
echo "   • Reduced chunk size (256 vs 512) for faster processing"
echo "   • Limited conversation history (3 vs 5) for memory efficiency"
echo "   • Optimized Ollama settings for 2-core VM"
echo "   • Memory monitoring and garbage collection"
echo "   • Threading limited to 2 cores"
echo "   • Reduced model context window for speed"
