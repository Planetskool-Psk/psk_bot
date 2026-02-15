"""Configuration management for the PSK Bot application."""

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
        self.embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "nomic-ai/nomic-embed-text-v1.5")
        self.embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", 16))

        self.chunk_size: int = int(os.getenv("CHUNK_SIZE", 512))
        self.chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", 100))
        self.top_k_results: int = int(os.getenv("TOP_K_RESULTS", 5))
        self.max_context_documents: int = int(os.getenv("CONTEXT_DOCUMENTS", 4))
        self.max_context_chars: int = int(os.getenv("CONTEXT_CHAR_LIMIT", 3000))

        self.ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma3:1b")
        self.ollama_keep_alive: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
        self.llm_timeout: int = int(os.getenv("LLM_TIMEOUT", 90))
        self.llm_num_predict: int = int(os.getenv("LLM_NUM_PREDICT", 384))
        self.llm_num_ctx: int = int(os.getenv("LLM_NUM_CTX", 2048))
        self.llm_num_thread: int = int(os.getenv("LLM_NUM_THREAD", 0))  # 0 = Ollama auto-detects
        self.llm_num_batch: int = int(os.getenv("LLM_NUM_BATCH", 512))
        self.llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", 0.2))
        self.llm_top_p: float = float(os.getenv("LLM_TOP_P", 0.8))
        self.llm_top_k: int = int(os.getenv("LLM_TOP_K", 20))

        self.max_conversation_history: int = int(os.getenv("MAX_CONVERSATION_HISTORY", 6))
        self.prompt_history_turns: int = int(os.getenv("PROMPT_HISTORY_TURNS", 3))

        # Server deployment settings
        self.server_workers: int = int(os.getenv("SERVER_WORKERS", 2))
        self.server_worker_connections: int = int(os.getenv("SERVER_WORKER_CONNECTIONS", 100))
        self.api_rate_limit: int = int(os.getenv("API_RATE_LIMIT", 30))  # requests per minute
        self.api_key: str = os.getenv("PSK_API_KEY", "")  # API key for robot hardware

        self.prompt_template: str = os.getenv(
            "PROMPT_TEMPLATE",
            (
                "You are a professional assistant. Answer the QUESTION using the CONTEXT below if relevant.\n"
                "Rules:\n"
                "- Be precise and direct. No filler, no essays.\n"
                "- Use short paragraphs or bullet points for clarity.\n"
                "- State facts confidently when supported by context.\n"
                "- If the context does not contain the answer, clearly state that the information is not available in the document.\n"
                "- Do not use outside knowledge or make assumptions beyond the provided context.\n"
                "- Keep a professional yet approachable tone.\n\n"
                "CONTEXT:\n{context}\n\n"
                "QUESTION: {question}\n\n"
                "ANSWER:"
            ),
        )

        self.secret_key: str = os.getenv("SECRET_KEY", "a_very_secret_key")

    @property
    def ollama_options(self) -> Dict[str, Any]:
        """Return generation options tuned for fast streaming."""
        opts: Dict[str, Any] = {
            "temperature": self.llm_temperature,
            "top_p": self.llm_top_p,
            "top_k": self.llm_top_k,
            "num_ctx": self.llm_num_ctx,
            "num_predict": self.llm_num_predict,
            "num_batch": self.llm_num_batch,
            "repeat_penalty": 1.1,
            "repeat_last_n": 64,
        }
        # Only set num_thread if explicitly configured (0 = let Ollama auto-detect)
        if self.llm_num_thread > 0:
            opts["num_thread"] = self.llm_num_thread
        return opts

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
