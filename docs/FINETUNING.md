# Fine-Tuning Gemma 3 1B for PSK Bot

This guide walks through fine-tuning the Gemma 3 1B model on your ASMS documentation so the bot learns the correct response style and domain knowledge.

## Overview

| Component | Details |
|-----------|---------|
| Base Model | `google/gemma-3-1b-it` (Gemma 3 1B Instruct) |
| Framework | Apple MLX with LoRA (4-bit QLoRA) |
| Hardware | Apple Silicon Mac (M1/M2/M3/M4), 8GB+ RAM |
| Training Time | ~15-60 minutes depending on dataset size |
| Disk Space | ~5GB (model + data + outputs) |

## Quick Start (One Command)

```bash
./scripts/finetune_pipeline.sh /Users/piyushchopra/Downloads/a3310_asms-help
```

This runs the entire pipeline: data prep → download model → train → export → import to Ollama.

## Step-by-Step Guide

### 1. Install Dependencies

```bash
pip install mlx mlx-lm pyyaml
```

### 2. Prepare Training Data

Parse your HTM/HTML documentation files into instruction-tuning format:

```bash
# Basic (fast, template-based Q&A generation)
python scripts/prepare_training_data.py /path/to/htm/folder

# With Ollama-generated Q&A pairs (slower, higher quality)
python scripts/prepare_training_data.py /path/to/htm/folder --use-ollama
```

**Options:**
| Flag | Description |
|------|-------------|
| `--output DIR` | Output directory (default: `training_data/`) |
| `--use-ollama` | Use Ollama to generate diverse Q&A pairs |
| `--max-files N` | Limit number of files to process |
| `--split 0.9` | Train/validation split ratio |

**Output files:**
- `training_data/train.jsonl` — Training examples
- `training_data/valid.jsonl` — Validation examples
- `training_data/stats.json` — Dataset statistics

### 3. Fine-Tune the Model

```bash
# Full pipeline (download + train + fuse)
python scripts/finetune.py

# Individual steps
python scripts/finetune.py --step download   # Download & quantize
python scripts/finetune.py --step train      # LoRA fine-tuning
python scripts/finetune.py --step fuse       # Fuse adapters
python scripts/finetune.py --step test       # Quick test
python scripts/finetune.py --step export     # Convert to GGUF
python scripts/finetune.py --step import     # Import to Ollama
```

**Training Parameters (8GB RAM safe defaults):**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `--iters` | 600 | Training iterations |
| `--batch-size` | 1 | Batch size (keep at 1 for 8GB) |
| `--learning-rate` | 1e-5 | Learning rate |
| `--lora-rank` | 8 | LoRA rank (lower = less memory) |
| `--max-seq-length` | 2048 | Max sequence length |

### 4. Export to Ollama

After training completes, export the model:

```bash
python scripts/finetune.py --step export   # Creates GGUF
python scripts/finetune.py --step import   # Imports to Ollama
```

Or manually:
```bash
ollama create psk-gemma3:1b -f models/Modelfile
```

### 5. Use in PSK Bot

Update `.env`:
```env
OLLAMA_MODEL=psk-gemma3:1b
```

Restart the server:
```bash
python run.py
```

## Directory Structure After Training

```
models/
├── gemma3-1b-4bit/          # 4-bit quantized base model
├── adapters/                # LoRA adapter weights
│   ├── adapters.safetensors
│   └── lora_config.yaml
├── gemma3-1b-finetuned/     # Fused model (base + adapters)
├── gemma3-1b-finetuned.gguf # GGUF for Ollama
└── Modelfile                # Ollama model definition
training_data/
├── train.jsonl
├── valid.jsonl
└── stats.json
```

## Troubleshooting

### Out of Memory (OOM)

If you get memory errors during training:
1. Reduce `--max-seq-length` to 1024
2. Ensure `--batch-size` is 1
3. Close other applications
4. Use `--lora-rank 4` for smaller adapters

### Training Loss Not Decreasing

1. Try a higher learning rate: `--learning-rate 5e-5`
2. Train for more iterations: `--iters 1000`
3. Generate more training data with `--use-ollama`

### Model Outputs Garbage

1. Make sure you fused the adapters: `python scripts/finetune.py --step fuse`
2. Try reducing the LoRA rank to avoid overfitting
3. Check that training data quality is good (inspect `training_data/train.jsonl`)

### GGUF Conversion Fails

The converter needs llama.cpp:
```bash
git clone --depth 1 https://github.com/ggerganov/llama.cpp
pip install -r llama.cpp/requirements.txt
python llama.cpp/convert_hf_to_gguf.py models/gemma3-1b-finetuned --outfile models/gemma3-1b-finetuned.gguf --outtype q8_0
```

## Training Data Format

Each training example is a ChatML conversation:

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are PSK Bot, a professional assistant for AlgoSec ASMS documentation..."
    },
    {
      "role": "user",
      "content": "Context:\n[document excerpt]\n\nQuestion: How do I configure email notifications?"
    },
    {
      "role": "assistant",
      "content": "To configure email notifications:\n\n• Set `SendEmailsToRequestors` to 1 to enable...\n• ..."
    }
  ]
}
```

## Re-Training After Document Updates

When documentation changes, re-run the pipeline:

```bash
# Regenerate training data
python scripts/prepare_training_data.py /path/to/updated/docs

# Re-train (optionally resume from previous adapters)
python scripts/finetune.py --step train

# Re-export
python scripts/finetune.py --step fuse
python scripts/finetune.py --step export
python scripts/finetune.py --step import
```
