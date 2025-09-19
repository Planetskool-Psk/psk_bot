"""Backwards-compatible config exports mapping to the new settings module."""

from gentari_bot.settings import settings

BASE_DIR = settings.base_dir
DATA_DIR = settings.data_dir
PDF_PATH = settings.pdf_path
VECTOR_STORE_DIR = settings.vector_store_dir
VECTOR_STORE_INDEX_NAME = settings.vector_store_index_name

EMBEDDING_MODEL_NAME = settings.embedding_model_name

CHUNK_SIZE = settings.chunk_size
CHUNK_OVERLAP = settings.chunk_overlap
TOP_K_RESULTS = settings.top_k_results

OLLAMA_BASE_URL = settings.ollama_base_url
OLLAMA_MODEL = settings.ollama_model

MAX_CONVERSATION_HISTORY = settings.max_conversation_history
PROMPT_TEMPLATE = settings.prompt_template

SECRET_KEY = settings.secret_key
