"""Configuration management for the Gentari Bot application."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()


class AppSettings:
    """Centralised, typed application settings with sensible defaults."""

    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        self.base_dir: Path = project_root
        self.data_dir: Path = Path(os.getenv("DATA_DIR", project_root / "data"))
        self.pdf_path: Path = Path(
            os.getenv("PDF_PATH", self.data_dir / "your_document.pdf")
        )

        vector_store_dir = os.getenv("VECTOR_STORE_DIR")
        self.vector_store_dir: Path = (
            Path(vector_store_dir)
            if vector_store_dir
            else project_root / "vector_store" / "faiss_index"
        )
        self.vector_store_index_name: str = os.getenv("VECTOR_STORE_INDEX_NAME", "faiss_index")

        # Supports sentence-transformers models from HuggingFace
        # nomic-ai/nomic-embed-text-v1.5 (768-dim, high quality)
        # all-MiniLM-L6-v2 (384-dim, lightweight)
        self.embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "nomic-ai/nomic-embed-text-v1.5")
        self.embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", 16))

        self.chunk_size: int = int(os.getenv("CHUNK_SIZE", 500))
        self.chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", 100))
        self.top_k_results: int = int(os.getenv("TOP_K_RESULTS", 5))
        self.max_context_documents: int = int(os.getenv("CONTEXT_DOCUMENTS", 5))
        self.max_context_chars: int = int(os.getenv("CONTEXT_CHAR_LIMIT", 3000))

        self.ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")  # Better accuracy model
        self.ollama_keep_alive: str = os.getenv("OLLAMA_KEEP_ALIVE", "120m")  # Keep loaded 2hrs
        self.llm_timeout: int = int(os.getenv("LLM_TIMEOUT", 60))
        self.llm_num_predict: int = int(os.getenv("LLM_NUM_PREDICT", 400))  # More room for complete answers
        self.llm_num_ctx: int = int(os.getenv("LLM_NUM_CTX", 4096))  # Larger context for full policy details
        self.llm_num_thread: int = int(os.getenv("LLM_NUM_THREAD", 4))  # Match VM cores
        self.llm_num_batch: int = int(os.getenv("LLM_NUM_BATCH", 256))  # Larger batch
        self.llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", 0.0))  # Zero temperature = no hallucination
        self.llm_top_p: float = float(os.getenv("LLM_TOP_P", 0.1))  # Very focused sampling
        self.llm_top_k: int = int(os.getenv("LLM_TOP_K", 1))  # Most deterministic

        self.max_conversation_history: int = int(os.getenv("MAX_CONVERSATION_HISTORY", 0))  # Disabled for speed
        self.prompt_history_turns: int = int(os.getenv("PROMPT_HISTORY_TURNS", 0))  # No history

        self.prompt_template: str = os.getenv(
            "PROMPT_TEMPLATE",
            (
                "You are Gia, a document assistant that helps employees find information from company documents.\n\n"
                "=== STRICT RULES (MUST FOLLOW) ===\n"
                "1. You can ONLY answer questions using the DOCUMENT CONTENT provided below\n"
                "2. You have NO external knowledge - you ONLY know what is in the document content\n"
                "3. If the question cannot be answered from the document content below, you MUST respond EXACTLY with:\n"
                "   'I couldn't find that information in the selected document. Please try a different question or select another document.'\n"
                "4. NEVER make up information, dates, numbers, names, or policies\n"
                "5. NEVER use your training knowledge to answer - ONLY the document content\n"
                "6. If someone asks about topics not in the document (weather, sports, general knowledge, etc.), use the response from rule 3\n\n"
                "=== RESPONSE STYLE ===\n"
                "- Be helpful and conversational\n"
                "- Quote specific details from the document when relevant\n"
                "- Keep responses concise and clear\n\n"
                "=== DOCUMENT CONTENT (Your ONLY source of information) ===\n{context}\n=== END OF DOCUMENT CONTENT ===\n\n"
                "Employee Question: {question}\n\n"
                "Answer ONLY from the document content above. If not found, say you couldn't find it:"
            ),
        )

        self.secret_key: str = os.getenv("SECRET_KEY", "a_very_secret_key")

    @property
    def ollama_options(self) -> Dict[str, Any]:
        """Return generation options tuned for fast streaming."""
        return {
            "temperature": self.llm_temperature,
            "top_p": self.llm_top_p,
            "top_k": self.llm_top_k,
            "num_ctx": self.llm_num_ctx,
            "num_predict": self.llm_num_predict,
            "num_thread": self.llm_num_thread,
            "num_batch": self.llm_num_batch,
            "repeat_penalty": 1.1,
            "repeat_last_n": 64,
        }

    def as_dict(self) -> Dict[str, Any]:
        """Return a serialisable view of the configuration."""
        return {
            "base_dir": str(self.base_dir),
            "data_dir": str(self.data_dir),
            "pdf_path": str(self.pdf_path),
            "vector_store_dir": str(self.vector_store_dir),
            "vector_store_index_name": self.vector_store_index_name,
            "embedding_model_name": self.embedding_model_name,
            "embedding_batch_size": self.embedding_batch_size,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "top_k_results": self.top_k_results,
            "max_context_documents": self.max_context_documents,
            "max_context_chars": self.max_context_chars,
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
            "ollama_keep_alive": self.ollama_keep_alive,
            "llm_timeout": self.llm_timeout,
            "llm_num_predict": self.llm_num_predict,
            "llm_num_ctx": self.llm_num_ctx,
            "llm_num_thread": self.llm_num_thread,
            "llm_temperature": self.llm_temperature,
            "llm_top_p": self.llm_top_p,
            "llm_top_k": self.llm_top_k,
            "max_conversation_history": self.max_conversation_history,
            "prompt_history_turns": self.prompt_history_turns,
            "prompt_template": self.prompt_template,
        }


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return a cached settings instance."""
    return AppSettings()


settings = get_settings()
