# ✅ Always do this FIRST
import eventlet
eventlet.monkey_patch()

import json
import logging
from pathlib import Path
from typing import List

from flask import Flask, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

# ========== Flask Setup ==========
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ========== Model Setup ==========
model_dir = "./llama-amplus"
tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
model = AutoModelForCausalLM.from_pretrained(model_dir)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
model.config.pad_token_id = tokenizer.pad_token_id

if torch.backends.mps.is_available():
    device = torch.device("mps")
    print(f"✅ Using MPS: {device}")
else:
    device = torch.device("cpu")
    print("⚠️ MPS not available. Using CPU.")

model = model.to(device)
model.eval()

# ========== Dataset & Vectorizer ==========
DATA_PATH = Path("lib/dataset/handbook_dataset.jsonl")

with open(DATA_PATH, "r") as f:
    records = [json.loads(line) for line in f]

questions: List[str] = [r["prompt"] for r in records]
answers: List[str] = [r["completion"] for r in records]

vectorizer = TfidfVectorizer()
X = vectorizer.fit_transform(questions)

# ========== Context & Few-shot Examples ==========
FEWSHOT_EXAMPLES = [
    "Q: What is the dress code policy at Amplus Solar?\nA: Business casual unless otherwise specified.",
    "Q: What are the optional holidays?\nA: Optional holidays include Holi, Eid, and Christmas.",
]
FEWSHOT_CONTEXT = "\n\n".join(FEWSHOT_EXAMPLES)

SYSTEM_CONTEXT = (
    "You are AmplusAssist, the official HR chatbot for Amplus Solar. "
    "You only answer based on Amplus HR policies. Politely decline out-of-scope topics like legal, tech, or personal advice."
)

# ========== Session Tracking ==========
session_histories = {}  # key = request.sid, value = list of messages


# ========== Conversation Handler ==========
def find_top_contexts(user_input: str, top_n: int = 3) -> List[str]:
    user_vec = vectorizer.transform([user_input])
    similarities = cosine_similarity(user_vec, X).flatten()
    top_indices = similarities.argsort()[::-1][:top_n]
    return [f"Q: {questions[i]}\nA: {answers[i]}" for i in top_indices]

def handle_conversation(user_message: str, context_history: str = "") -> str:
    top_contexts = find_top_contexts(user_message)
    context_snippets = "\n\n".join(top_contexts)

    prompt = f"""
You are AmplusAssist, the official HR chatbot for Amplus Solar.
You only answer based on Amplus HR policies.

Here are some examples:
{FEWSHOT_CONTEXT}

Relevant Policy Context:
{context_snippets}

User Question: {user_message}

AmplusAssist Answer:"""

    inputs = tokenizer(prompt, return_tensors="pt").to(device)

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=50,
            temperature=0.9,
            top_p=0.9,
            do_sample=True,
            pad_token_id=tokenizer.pad_token_id,
        )

    full_output = tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()

    # Only extract content after "AmplusAssist Answer:"
    answer_prefix = "AmplusAssist Answer:"
    if answer_prefix in full_output:
        return full_output.split(answer_prefix)[-1].strip()

    # Fallback if pattern is not respected
    return full_output


# ========== WebSocket Events ==========
@socketio.on("connect")
def on_connect():
    sid = request.sid
    session_histories[sid] = []
    print(f"🟢 Client connected: {sid}")
    emit("connected", {"msg": "You're connected to AmplusAssist!"})


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    session_histories.pop(sid, None)
    print(f"🔴 Client disconnected: {sid}")


@socketio.on("message")
def handle_message(data):
    sid = request.sid
    history = session_histories.get(sid, [])

    user_msg = data.get("message", "").strip() if isinstance(data, dict) else str(data).strip()

    if not user_msg:
        emit("message", {"msg": "⚠️ Empty message received."})
        return

    print(f"📨 [{sid}] Message received: {user_msg}")

    # Start a background task to avoid blocking
    socketio.start_background_task(process_message, sid, user_msg, history)


def process_message(sid, user_msg, history):
    try:
        context_text = "\n".join(history)
        response = handle_conversation(user_msg, context_text)

        history.append(f"User: {user_msg}")
        history.append(f"AmplusAssist: {response}")
        session_histories[sid] = history

        print(f"🤖 [{sid}] Responding: {response}")
        socketio.emit("message", response, to=sid)

    except Exception as e:
        print(f"❌ [{sid}] Error: {e}")
        socketio.emit("message", "⚠️ Sorry, something went wrong.", to=sid)

# ========== Main App Runner ==========
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("✅ AmplusAssist is live on port 5001")
    socketio.run(app, host="0.0.0.0", port=5001)
