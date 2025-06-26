import json
import pandas as pd
from datasets import Dataset

# Load and reformat the dataset
with open("lib/dataset/handbook_dataset.jsonl", "r", encoding="utf-8") as f:
    content = f.read()

# Convert newline-separated JSON objects to list
json_objects = "[" + content.replace("}\n{", "},\n{") + "]"
data = json.loads(json_objects)

# Format to instruction-tuning style
formatted = [
    {
        "prompt": item["prompt"],
        "completion": item["completion"],
        "text": f"### Question: {item['prompt']}\n### Answer: {item['completion']}",
    }
    for item in data
]

# Convert to HuggingFace Dataset
dataset = Dataset.from_pandas(pd.DataFrame(formatted))
dataset = dataset.train_test_split(test_size=0.1)
dataset.save_to_disk("amplus_handbook_dataset")
