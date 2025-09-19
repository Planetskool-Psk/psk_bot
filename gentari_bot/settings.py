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

        self.embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

        self.chunk_size: int = int(os.getenv("CHUNK_SIZE", 384))
        self.chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", 64))
        self.top_k_results: int = int(os.getenv("TOP_K_RESULTS", 2))

        self.ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma3:1b")

        self.max_conversation_history: int = int(os.getenv("MAX_CONVERSATION_HISTORY", 4))

        self.prompt_template: str = os.getenv(
            "PROMPT_TEMPLATE",
            (
                "You are Gia (Gentari Intelligence Assistant), a helpful HR assistant. Answer "
                "questions using ONLY the provided context.\n\nCONTEXT:\n{context}\n\nPREVIOUS "
                "CONVERSATION:\n{history}\n\nQUESTION: {question}\n\nINSTRUCTIONS:\n- Use only information "
                "from the context above\n- If context doesn't contain the answer, say \"I cannot find this information "
                "in the document. Please contact the HR team.\"\n- Be concise and helpful\n- Do not mention page "
                "numbers or sections\n\nANSWER:"
            ),
        )

        self.secret_key: str = os.getenv("SECRET_KEY", "a_very_secret_key")

    def as_dict(self) -> Dict[str, Any]:
        """Return a serialisable view of the configuration."""
        return {
            "base_dir": str(self.base_dir),
            "data_dir": str(self.data_dir),
            "pdf_path": str(self.pdf_path),
            "vector_store_dir": str(self.vector_store_dir),
            "vector_store_index_name": self.vector_store_index_name,
            "embedding_model_name": self.embedding_model_name,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "top_k_results": self.top_k_results,
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
            "max_conversation_history": self.max_conversation_history,
            "prompt_template": self.prompt_template,
        }


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return a cached settings instance."""
    return AppSettings()


settings = get_settings()
