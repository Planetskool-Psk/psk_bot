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

CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 384))  # Increased for better context while staying optimized
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", 64))  # Increased overlap for better continuity
TOP_K_RESULTS = int(os.environ.get("TOP_K_RESULTS", 2))  # Use 2 documents for better context


# --- Ollama LLM ---
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:1b")


# --- Chat History ---
MAX_CONVERSATION_HISTORY = int(os.environ.get("MAX_CONVERSATION_HISTORY", 4))  # Increased for better context while staying memory efficient

# --- Prompt Template ---
PROMPT_TEMPLATE = os.environ.get("PROMPT_TEMPLATE", """You are Gia (Gentari Intelligence Assistant), a helpful HR assistant. Answer questions using ONLY the provided context.

CONTEXT:
{context}

PREVIOUS CONVERSATION:
{history}

QUESTION: {question}

INSTRUCTIONS:
- Use only information from the context above
- If context doesn't contain the answer, say "I cannot find this information in the document. Please contact the HR team."
- Be concise and helpful
- Do not mention page numbers or sections

ANSWER:""")

# --- Flask Secret Key ---
SECRET_KEY = os.environ.get("SECRET_KEY", "a_very_secret_key")
