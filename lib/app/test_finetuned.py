### This script is for testing the Llama-Amplus model on macOS with MPS support.

# from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
# import torch

# # Detect MPS or fallback to CPU
# if torch.backends.mps.is_available():
#     device = torch.device("mps")
#     print(f"MPS device available: {device}")
# else:
#     device = torch.device("cpu")
#     print("MPS device not available. Falling back to CPU.")

# # Load fine-tuned model and tokenizer
# model_dir = "./llama-amplus"
# tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
# model = AutoModelForCausalLM.from_pretrained(model_dir)

# # Set padding token if needed
# if tokenizer.pad_token is None:
#     tokenizer.pad_token = tokenizer.eos_token
# model.config.pad_token_id = tokenizer.pad_token_id

# # Move model to appropriate device
# model = model.to(device)

# # Build text-generation pipeline
# generator = pipeline("text-generation", model=model, tokenizer=tokenizer, device=-1)

# # Inference
# prompt = "### Question: What are the optional holidays and Name of Holidays also?\n### Answer:"
# print("Generating response...")
# output = generator(prompt, max_new_tokens=50, do_sample=False)[0]["generated_text"]

# print("\n--- Response ---")
# print(output)


import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# 🔍 Detect device (MPS if available, else CPU)
if torch.backends.mps.is_available():
    device = torch.device("mps")
    print(f"✅ Using MPS device: {device}")
else:
    device = torch.device("cpu")
    print("⚠️ MPS not available, using CPU.")

# 📦 Load fine-tuned model and tokenizer
model_dir = "./llama-amplus"
tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
model = AutoModelForCausalLM.from_pretrained(model_dir)

# 🩹 Add padding token if needed
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
model.config.pad_token_id = tokenizer.pad_token_id

# Move model to device
model = model.to(device)
model.eval()

# 🧪 Input
prompt = "### Question: Question: What are the optional holidays Dates and Names?\n### Answer:"
inputs = tokenizer(prompt, return_tensors="pt").to(device)

# 🧠 Generate
with torch.no_grad():
    output_ids = model.generate(
        **inputs,
        max_new_tokens=50,
        temperature=0.7,
        do_sample=True,
        top_p=0.9,
        pad_token_id=tokenizer.pad_token_id,
    )

# 🔁 Decode output
generated_text = tokenizer.decode(output_ids[0], skip_special_tokens=True)

print("\n--- Response ---")
print(generated_text)
