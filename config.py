# /rag-chatbot-ollama/config.py

import os
from dotenv import load_dotenv
load_dotenv()

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
VECTOR_STORE_DIR = os.environ.get("VECTOR_STORE_DIR", os.path.join(BASE_DIR, "vector_store", "faiss_index"))
PDF_PATH = os.path.join(
    DATA_DIR, "your_document.pdf"
)  # <-- IMPORTANT: Name of your PDF file

# --- Vector Store & Embeddings ---

EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
VECTOR_STORE_INDEX_NAME = os.environ.get("VECTOR_STORE_INDEX_NAME", "faiss_index")

# --- RAG ---

CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 600))  # Reduced for faster, more focused context
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", 50))
TOP_K_RESULTS = int(os.environ.get("TOP_K_RESULTS", 3))


# --- Ollama LLM ---
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma2:2b")


# --- Chat History ---
MAX_CONVERSATION_HISTORY = int(os.environ.get("MAX_CONVERSATION_HISTORY", 5))

# --- Prompt Template ---
PROMPT_TEMPLATE = os.environ.get("PROMPT_TEMPLATE", """
SYSTEM INSTRUCTIONS:
You are a helpful AI hr assistant named as Gia (Gentari Intelligence Assistant). Your task is to answer user questions based *only* on the provided context document.
- If the context contains the answer, provide a clear and concise response based on that information.
- If the context does not contain enough information to answer the question, you must state that you cannot answer this specific question ask the hr from hr team.
- Do not use any external knowledge or information you were trained on.
- Do not show the page number or section number in your messages.

CONTEXT FROM THE DOCUMENT:
{context}

CONVERSATION HISTORY:
{history}

USER'S QUESTION:
{question}

YOUR ANSWER:
""")

# --- Flask Secret Key ---
SECRET_KEY = os.environ.get("SECRET_KEY", "a_very_secret_key")
