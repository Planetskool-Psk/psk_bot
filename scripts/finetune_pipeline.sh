#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# Fine-tune Gemma 3 1B on ASMS Documentation (Apple Silicon)
# ═══════════════════════════════════════════════════════════════════════
#
# This script runs the complete fine-tuning pipeline:
#   1. Install dependencies (mlx-lm, pyyaml)
#   2. Prepare training data from HTM files
#   3. Download & quantize Gemma 3 1B to 4-bit
#   4. Fine-tune with LoRA
#   5. Fuse adapters
#   6. Export to GGUF & import into Ollama
#
# Usage:
#   ./scripts/finetune_pipeline.sh /path/to/htm/folder
#   ./scripts/finetune_pipeline.sh /path/to/htm/folder --use-ollama
#
# Requirements:
#   - macOS with Apple Silicon (M1/M2/M3/M4)
#   - Python 3.10+ with venv
#   - Ollama installed and running
#   - ~8GB free RAM + ~5GB disk space
#
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn(){ echo -e "${YELLOW}[!]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ─── Parse Args ─────────────────────────────────────────────────────

INPUT_FOLDER="${1:-}"
USE_OLLAMA_FLAG=""

if [[ -z "$INPUT_FOLDER" ]]; then
    err "Usage: $0 /path/to/htm/folder [--use-ollama]"
fi

if [[ ! -d "$INPUT_FOLDER" ]]; then
    err "Folder not found: $INPUT_FOLDER"
fi

shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --use-ollama) USE_OLLAMA_FLAG="--use-ollama" ;;
        *) warn "Unknown argument: $1" ;;
    esac
    shift
done

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
log "Project directory: $PROJECT_DIR"

# ─── Step 1: Install Dependencies ──────────────────────────────────

log "Step 1/6: Installing dependencies..."

# Use the project's venv if available
PYTHON="python3"
if [[ -f "venv/bin/python3" ]]; then
    PYTHON="venv/bin/python3"
fi

$PYTHON -m pip install --quiet mlx mlx-lm pyyaml 2>/dev/null || {
    warn "pip install failed, trying with --break-system-packages..."
    $PYTHON -m pip install --quiet --break-system-packages mlx mlx-lm pyyaml
}
ok "Dependencies installed"

# ─── Step 2: Prepare Training Data ────────────────────────────────

log "Step 2/6: Preparing training data from $INPUT_FOLDER..."

$PYTHON scripts/prepare_training_data.py "$INPUT_FOLDER" \
    --output training_data \
    $USE_OLLAMA_FLAG

if [[ ! -f "training_data/train.jsonl" ]]; then
    err "Training data generation failed"
fi

TRAIN_COUNT=$(wc -l < training_data/train.jsonl | tr -d ' ')
VALID_COUNT=$(wc -l < training_data/valid.jsonl | tr -d ' ')
ok "Training data ready: $TRAIN_COUNT train, $VALID_COUNT validation examples"

# ─── Step 3: Download & Quantize Model ────────────────────────────

log "Step 3/6: Downloading & quantizing Gemma 3 1B..."

if [[ -f "models/gemma3-1b-4bit/config.json" ]]; then
    ok "Quantized model already exists (skipping download)"
else
    $PYTHON -m mlx_lm.convert \
        --hf-path google/gemma-3-1b-it \
        --mlx-path models/gemma3-1b-4bit \
        -q
    ok "Model downloaded and quantized to 4-bit"
fi

# ─── Step 4: Fine-Tune with LoRA ──────────────────────────────────

log "Step 4/6: Fine-tuning with LoRA (this takes 15-60 minutes)..."

# Determine iterations based on dataset size
ITERS=600
if [[ $TRAIN_COUNT -gt 2000 ]]; then
    ITERS=1000
elif [[ $TRAIN_COUNT -lt 200 ]]; then
    ITERS=300
fi

log "Training for $ITERS iterations (batch=1, lr=1e-5, rank=8)..."

$PYTHON -m mlx_lm.lora \
    --model models/gemma3-1b-4bit \
    --train \
    --data training_data \
    --adapter-path models/adapters \
    --iters $ITERS \
    --batch-size 1 \
    --learning-rate 1e-5 \
    --lora-layers 8 \
    --val-batches 25 \
    --steps-per-report 10 \
    --steps-per-eval 50 \
    --save-every 100 \
    --max-seq-length 2048 \
    --grad-checkpoint

ok "LoRA fine-tuning complete"

# ─── Step 5: Fuse Adapters ────────────────────────────────────────

log "Step 5/6: Fusing LoRA adapters into model..."

$PYTHON -m mlx_lm.fuse \
    --model models/gemma3-1b-4bit \
    --adapter-path models/adapters \
    --save-path models/gemma3-1b-finetuned

ok "Adapters fused"

# ─── Step 6: Export to Ollama ─────────────────────────────────────

log "Step 6/6: Exporting to Ollama..."

# Check if llama.cpp converter exists
CONVERTER=""
for path in "$HOME/llama.cpp/convert_hf_to_gguf.py" \
            "/usr/local/bin/convert_hf_to_gguf.py" \
            "llama.cpp/convert_hf_to_gguf.py"; do
    if [[ -f "$path" ]]; then
        CONVERTER="$path"
        break
    fi
done

if [[ -z "$CONVERTER" ]]; then
    warn "llama.cpp converter not found. Cloning llama.cpp..."
    if [[ ! -d "llama.cpp" ]]; then
        git clone --depth 1 https://github.com/ggerganov/llama.cpp
        $PYTHON -m pip install --quiet -r llama.cpp/requirements.txt 2>/dev/null || true
    fi
    CONVERTER="llama.cpp/convert_hf_to_gguf.py"
fi

mkdir -p models
$PYTHON "$CONVERTER" models/gemma3-1b-finetuned \
    --outfile models/gemma3-1b-finetuned.gguf \
    --outtype q8_0

ok "GGUF model created"

# Create Ollama Modelfile
GGUF_ABS="$(cd models && pwd)/gemma3-1b-finetuned.gguf"
cat > models/Modelfile << EOF
FROM $GGUF_ABS

PARAMETER temperature 0.3
PARAMETER top_p 0.8
PARAMETER top_k 20
PARAMETER num_ctx 4096
PARAMETER repeat_penalty 1.1

SYSTEM """You are PSK Bot, a professional assistant for AlgoSec ASMS documentation. Answer questions accurately based on the provided documentation context. Use bullet points and clear formatting. Be precise and direct. If the information is not available in the provided context, clearly state that."""

TEMPLATE """{{ if .System }}<start_of_turn>system
{{ .System }}<end_of_turn>
{{ end }}{{ if .Prompt }}<start_of_turn>user
{{ .Prompt }}<end_of_turn>
<start_of_turn>model
{{ end }}{{ .Response }}<end_of_turn>"""
EOF

# Import to Ollama
MODEL_NAME="psk-gemma3:1b"
ollama create "$MODEL_NAME" -f models/Modelfile && {
    ok "Model imported to Ollama as: $MODEL_NAME"
} || {
    warn "Ollama import failed. You can manually import with:"
    echo "  ollama create $MODEL_NAME -f models/Modelfile"
}

# ─── Update .env ──────────────────────────────────────────────────

if [[ -f ".env" ]]; then
    if grep -q "^OLLAMA_MODEL=" .env; then
        sed -i.bak "s/^OLLAMA_MODEL=.*/OLLAMA_MODEL=$MODEL_NAME/" .env
        rm -f .env.bak
        ok "Updated .env: OLLAMA_MODEL=$MODEL_NAME"
    fi
fi

# ─── Done ─────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "${GREEN}  Fine-tuning complete!${NC}"
echo ""
echo "  Model:     $MODEL_NAME"
echo "  GGUF:      models/gemma3-1b-finetuned.gguf"
echo "  Adapters:  models/adapters/"
echo ""
echo "  Quick test:"
echo "    ollama run $MODEL_NAME"
echo ""
echo "  To use in PSK Bot:"
echo "    1. Ensure OLLAMA_MODEL=$MODEL_NAME in .env"
echo "    2. Restart the server: python run.py"
echo "═══════════════════════════════════════════════════════════════"
