#!/usr/bin/env python3
"""Fine-tune Gemma 3 1B using MLX LoRA on Apple Silicon.

This script handles the full fine-tuning pipeline:
  1. Download/quantize the base model
  2. Configure LoRA adapters
  3. Train on the prepared JSONL data
  4. Fuse adapters into the model
  5. Optionally convert to GGUF for Ollama

Usage:
    python scripts/finetune.py                      # Full pipeline
    python scripts/finetune.py --step train          # Only train
    python scripts/finetune.py --step fuse           # Only fuse adapters
    python scripts/finetune.py --step export         # Only export to GGUF + Ollama

Prerequisites:
    pip install mlx-lm

For 8GB RAM Macs, the script uses 4-bit quantization (QLoRA) to fit in memory.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ─── Configuration ──────────────────────────────────────────────────────

BASE_MODEL = "google/gemma-3-1b-it"  # HuggingFace model ID
QUANTIZED_MODEL_DIR = Path("models/gemma3-1b-4bit")
ADAPTER_DIR = Path("models/adapters")
FUSED_MODEL_DIR = Path("models/gemma3-1b-finetuned")
GGUF_OUTPUT = Path("models/gemma3-1b-finetuned.gguf")
TRAINING_DATA_DIR = Path("training_data")

# LoRA Configuration (optimized for 8GB RAM)
LORA_CONFIG = {
    "num_layers": 8,          # Number of layers to apply LoRA to
    "lora_parameters": {
        "rank": 8,            # LoRA rank (lower = less memory, 8 is good balance)
        "alpha": 16,          # LoRA alpha (typically 2x rank)
        "dropout": 0.05,      # Regularization
        "scale": 2.0,         # alpha / rank
    },
}

# Training Configuration (optimized for 8GB RAM)
TRAIN_CONFIG = {
    "iters": 600,             # Training iterations
    "batch_size": 1,          # Batch size (1 for 8GB RAM)
    "learning_rate": 1e-5,    # Learning rate
    "lora_layers": 8,         # Must match num_layers above
    "val_batches": 25,        # Validation batches
    "steps_per_report": 10,   # Report every N steps
    "steps_per_eval": 50,     # Evaluate every N steps
    "save_every": 100,        # Save checkpoint every N steps
    "max_seq_length": 2048,   # Max sequence length (reduce if OOM)
    "grad_checkpoint": True,  # Gradient checkpointing (saves memory)
}


def run_cmd(cmd: list, desc: str = "", check: bool = True) -> subprocess.CompletedProcess:
    """Run a command with nice output."""
    if desc:
        print(f"\n{'─'*60}")
        print(f"  {desc}")
        print(f"{'─'*60}")
    print(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, check=check)
    return result


def check_prerequisites():
    """Verify required packages are installed."""
    missing = []

    try:
        import mlx
    except ImportError:
        missing.append("mlx")

    try:
        import mlx_lm
    except ImportError:
        missing.append("mlx-lm")

    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        print(f"Install with: pip install {' '.join(missing)}")
        sys.exit(1)

    # Check training data
    train_file = TRAINING_DATA_DIR / "train.jsonl"
    valid_file = TRAINING_DATA_DIR / "valid.jsonl"
    if not train_file.exists() or not valid_file.exists():
        print(f"Training data not found at {TRAINING_DATA_DIR}/")
        print("Run: python scripts/prepare_training_data.py /path/to/htm/folder")
        sys.exit(1)

    # Count examples
    with open(train_file) as f:
        train_count = sum(1 for _ in f)
    with open(valid_file) as f:
        valid_count = sum(1 for _ in f)
    print(f"Training data: {train_count} train, {valid_count} validation examples")

    if train_count < 50:
        print("Warning: Very few training examples. Consider using --use-ollama in data preparation.")


def step_download_and_quantize():
    """Download Gemma 3 1B and quantize to 4-bit for memory efficiency."""
    if QUANTIZED_MODEL_DIR.exists() and (QUANTIZED_MODEL_DIR / "config.json").exists():
        print(f"Quantized model already exists at {QUANTIZED_MODEL_DIR}")
        return

    QUANTIZED_MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading and quantizing {BASE_MODEL} to 4-bit...")
    print("This may take a few minutes on first run (downloading ~2GB)...")

    run_cmd(
        [
            sys.executable, "-m", "mlx_lm.convert",
            "--hf-path", BASE_MODEL,
            "--mlx-path", str(QUANTIZED_MODEL_DIR),
            "-q",  # Quantize to 4-bit
        ],
        desc="Download & Quantize Model",
    )

    print(f"Model saved to {QUANTIZED_MODEL_DIR}")


def step_train():
    """Fine-tune using LoRA."""
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)

    # Write LoRA config
    lora_config_path = ADAPTER_DIR / "lora_config.yaml"
    import yaml
    with open(lora_config_path, "w") as f:
        yaml.dump(LORA_CONFIG, f)

    cmd = [
        sys.executable, "-m", "mlx_lm.lora",
        "--model", str(QUANTIZED_MODEL_DIR),
        "--train",
        "--data", str(TRAINING_DATA_DIR),
        "--adapter-path", str(ADAPTER_DIR),
        "--iters", str(TRAIN_CONFIG["iters"]),
        "--batch-size", str(TRAIN_CONFIG["batch_size"]),
        "--learning-rate", str(TRAIN_CONFIG["learning_rate"]),
        "--lora-layers", str(TRAIN_CONFIG["lora_layers"]),
        "--val-batches", str(TRAIN_CONFIG["val_batches"]),
        "--steps-per-report", str(TRAIN_CONFIG["steps_per_report"]),
        "--steps-per-eval", str(TRAIN_CONFIG["steps_per_eval"]),
        "--save-every", str(TRAIN_CONFIG["save_every"]),
        "--max-seq-length", str(TRAIN_CONFIG["max_seq_length"]),
    ]

    if TRAIN_CONFIG.get("grad_checkpoint"):
        cmd.append("--grad-checkpoint")

    run_cmd(cmd, desc="LoRA Fine-Tuning")

    print(f"\nAdapters saved to {ADAPTER_DIR}")
    print("Training complete!")


def step_fuse():
    """Fuse LoRA adapters into the base model."""
    if not ADAPTER_DIR.exists() or not (ADAPTER_DIR / "adapters.safetensors").exists():
        print(f"No adapters found at {ADAPTER_DIR}")
        print("Run training first: python scripts/finetune.py --step train")
        sys.exit(1)

    FUSED_MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)

    run_cmd(
        [
            sys.executable, "-m", "mlx_lm.fuse",
            "--model", str(QUANTIZED_MODEL_DIR),
            "--adapter-path", str(ADAPTER_DIR),
            "--save-path", str(FUSED_MODEL_DIR),
        ],
        desc="Fuse LoRA Adapters",
    )

    print(f"Fused model saved to {FUSED_MODEL_DIR}")


def step_test():
    """Quick test of the fine-tuned model."""
    model_path = str(FUSED_MODEL_DIR) if FUSED_MODEL_DIR.exists() else str(QUANTIZED_MODEL_DIR)
    adapter_path = str(ADAPTER_DIR) if not FUSED_MODEL_DIR.exists() and ADAPTER_DIR.exists() else None

    cmd = [
        sys.executable, "-m", "mlx_lm.generate",
        "--model", model_path,
        "--prompt", "What is FireFlow in AlgoSec ASMS?",
        "--max-tokens", "200",
    ]

    if adapter_path:
        cmd.extend(["--adapter-path", adapter_path])

    run_cmd(cmd, desc="Test Fine-Tuned Model")


def step_export_gguf():
    """Convert MLX model to GGUF format for Ollama."""
    if not FUSED_MODEL_DIR.exists():
        print(f"Fused model not found at {FUSED_MODEL_DIR}")
        print("Run fuse first: python scripts/finetune.py --step fuse")
        sys.exit(1)

    GGUF_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # Check if llama.cpp convert script is available
    convert_script = None
    possible_paths = [
        Path.home() / "llama.cpp" / "convert_hf_to_gguf.py",
        Path("/usr/local/bin/convert_hf_to_gguf.py"),
        Path("llama.cpp/convert_hf_to_gguf.py"),
    ]

    for p in possible_paths:
        if p.exists():
            convert_script = p
            break

    if not convert_script:
        print("\nllama.cpp conversion tool not found.")
        print("To install it:")
        print("  git clone https://github.com/ggerganov/llama.cpp")
        print("  cd llama.cpp && pip install -r requirements.txt")
        print(f"\nThen run: python llama.cpp/convert_hf_to_gguf.py {FUSED_MODEL_DIR} --outfile {GGUF_OUTPUT} --outtype q8_0")
        return False

    run_cmd(
        [
            sys.executable, str(convert_script),
            str(FUSED_MODEL_DIR),
            "--outfile", str(GGUF_OUTPUT),
            "--outtype", "q8_0",  # Q8 quantization for good quality
        ],
        desc="Convert to GGUF",
    )

    print(f"GGUF model saved to {GGUF_OUTPUT}")
    return True


def step_import_ollama():
    """Create Ollama model from GGUF file."""
    if not GGUF_OUTPUT.exists():
        print(f"GGUF file not found: {GGUF_OUTPUT}")
        print("Run export first: python scripts/finetune.py --step export")
        sys.exit(1)

    # Create Modelfile
    modelfile_path = Path("models/Modelfile")
    modelfile_content = f"""FROM {GGUF_OUTPUT.resolve()}

PARAMETER temperature 0.3
PARAMETER top_p 0.8
PARAMETER top_k 20
PARAMETER num_ctx 4096
PARAMETER repeat_penalty 1.1

SYSTEM \"\"\"You are PSK Bot, a professional assistant for AlgoSec ASMS documentation. Answer questions accurately based on the provided documentation context. Use bullet points and clear formatting. Be precise and direct. If the information is not available in the provided context, clearly state that.\"\"\"

TEMPLATE \"\"\"{{{{ if .System }}}}<start_of_turn>system
{{{{ .System }}}}<end_of_turn>
{{{{ end }}}}{{{{ if .Prompt }}}}<start_of_turn>user
{{{{ .Prompt }}}}<end_of_turn>
<start_of_turn>model
{{{{ end }}}}{{{{ .Response }}}}<end_of_turn>\"\"\"
"""

    modelfile_path.write_text(modelfile_content)
    print(f"Modelfile created at {modelfile_path}")

    # Create the model in Ollama
    model_name = "psk-gemma3:1b"
    run_cmd(
        ["ollama", "create", model_name, "-f", str(modelfile_path)],
        desc=f"Import to Ollama as '{model_name}'",
        check=False,
    )

    print(f"\nModel imported as: {model_name}")
    print(f"Test with: ollama run {model_name}")
    print(f"\nTo use in PSK Bot, update .env:")
    print(f"  OLLAMA_MODEL={model_name}")

    return model_name


def step_update_env(model_name: str = "psk-gemma3:1b"):
    """Update .env to use the fine-tuned model."""
    env_path = Path(".env")
    if not env_path.exists():
        print(".env file not found")
        return

    content = env_path.read_text()
    import re
    new_content = re.sub(
        r'^OLLAMA_MODEL=.*$',
        f'OLLAMA_MODEL={model_name}',
        content,
        flags=re.MULTILINE,
    )

    if new_content != content:
        env_path.write_text(new_content)
        print(f"Updated .env: OLLAMA_MODEL={model_name}")
    else:
        print(f".env already uses {model_name}")


# ─── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune Gemma 3 1B on ASMS documentation using MLX LoRA"
    )
    parser.add_argument(
        "--step",
        choices=["all", "download", "train", "test", "fuse", "export", "import", "update-env"],
        default="all",
        help="Which step to run (default: all)",
    )
    parser.add_argument("--iters", type=int, help="Override training iterations")
    parser.add_argument("--batch-size", type=int, help="Override batch size")
    parser.add_argument("--learning-rate", type=float, help="Override learning rate")
    parser.add_argument("--lora-rank", type=int, help="Override LoRA rank")
    parser.add_argument("--max-seq-length", type=int, help="Override max sequence length")
    args = parser.parse_args()

    # Override config from args
    if args.iters:
        TRAIN_CONFIG["iters"] = args.iters
    if args.batch_size:
        TRAIN_CONFIG["batch_size"] = args.batch_size
    if args.learning_rate:
        TRAIN_CONFIG["learning_rate"] = args.learning_rate
    if args.lora_rank:
        LORA_CONFIG["lora_parameters"]["rank"] = args.lora_rank
        LORA_CONFIG["lora_parameters"]["alpha"] = args.lora_rank * 2
    if args.max_seq_length:
        TRAIN_CONFIG["max_seq_length"] = args.max_seq_length

    os.chdir(Path(__file__).resolve().parent.parent)
    print(f"Working directory: {os.getcwd()}")

    steps = {
        "download": step_download_and_quantize,
        "train": step_train,
        "test": step_test,
        "fuse": step_fuse,
        "export": step_export_gguf,
        "import": step_import_ollama,
        "update-env": lambda: step_update_env(),
    }

    if args.step == "all":
        check_prerequisites()
        step_download_and_quantize()
        step_train()
        step_fuse()
        step_test()
        success = step_export_gguf()
        if success:
            model_name = step_import_ollama()
            if model_name:
                step_update_env(model_name)
    else:
        if args.step in ("train", "all"):
            check_prerequisites()
        steps[args.step]()

    print("\n" + "=" * 60)
    print("Done! Next steps:")
    print("  1. Test: ollama run psk-gemma3:1b")
    print("  2. Update .env: OLLAMA_MODEL=psk-gemma3:1b")
    print("  3. Restart PSK Bot server")
    print("=" * 60)


if __name__ == "__main__":
    main()
