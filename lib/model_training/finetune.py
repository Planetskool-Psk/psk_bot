from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
import torch
from peft import get_peft_model, LoraConfig, TaskType
from datasets import load_from_disk

# Load dataset
dataset = load_from_disk("amplus_handbook_dataset")

# Load base model
model_id = "meta-llama/Llama-3.2-1B"  # Replace with your chosen model if needed
model = AutoModelForCausalLM.from_pretrained(model_id)
model = model.to(torch.device("cpu"))  # Force CPU-only execution

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)

# Add pad token if missing
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
model.config.pad_token_id = tokenizer.pad_token_id

# ✅ Save tokenizer for later inference
tokenizer.save_pretrained("./llama-amplus")


# Tokenization function
def tokenize(example):
    return tokenizer(
        example["text"], truncation=True, padding="max_length", max_length=512
    )


# Apply tokenization
tokenized = dataset.map(tokenize, batched=True)

# LoRA config
peft_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=8,
    lora_alpha=16,
    lora_dropout=0.1,
    bias="none",
)

model = get_peft_model(model, peft_config)

# Training args
training_args = TrainingArguments(
    output_dir="./llama-amplus",
    per_device_train_batch_size=1,
    per_device_eval_batch_size=1,
    max_steps=5,  # Quick test
    save_strategy="no",
    eval_strategy="no",
    logging_steps=1,
    use_cpu=True,  # Use CPU
)

# Trainer setup
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized["train"],
    eval_dataset=tokenized["test"],
    data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
)

# Run training
print("Starting trainer...")
trainer.train()
print("Training complete!")

# ✅ Save model weights
model.save_pretrained("./llama-amplus")
