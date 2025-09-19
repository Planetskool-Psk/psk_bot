"""Vector store management backed by FAISS."""

import pickle
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from gentari_bot.logging import get_logger
from gentari_bot.settings import AppSettings, settings

logger = get_logger(__name__)


class VectorStoreService:
    """Coordinate embedding generation, persistence, and semantic search."""

    def __init__(self, *, config: AppSettings = settings) -> None:
        self._config = config
        self._lock = Lock()
        self._embedding_model: Optional[SentenceTransformer] = None
        self._index: Optional[Any] = None
        self._documents: Optional[List[str]] = None

        base_path = Path(self._config.vector_store_dir)
        self._index_path = base_path / f"{self._config.vector_store_index_name}.faiss"
        self._docs_path = base_path / f"{self._config.vector_store_index_name}.pkl"
        self._ensure_store_directory()

        logger.info("Preloading embedding model: %s", self._config.embedding_model_name)
        self._get_embedding_model()

    def _ensure_store_directory(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_embedding_model(self) -> SentenceTransformer:
        with self._lock:
            if self._embedding_model is None:
                self._embedding_model = SentenceTransformer(
                    self._config.embedding_model_name,
                    device="cpu",
                    trust_remote_code=False,
                )
                try:
                    self._embedding_model.half()  # type: ignore[attr-defined]
                    logger.info("Embedding model switched to half precision")
                except AttributeError:
                    logger.debug("Half precision unavailable; using full precision")
        return self._embedding_model

    def create_and_save_store(self, chunks: Iterable[str], *, batch_size: int = 32) -> None:
        documents = [chunk.strip() for chunk in chunks if chunk and chunk.strip()]
        if not documents:
            logger.error("No chunks provided to create vector store")
            return

        model = self._get_embedding_model()
        embeddings: List[np.ndarray] = []
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            batch_embeddings = model.encode(batch, show_progress_bar=False, batch_size=16)
            embeddings.append(batch_embeddings)

        matrix = np.vstack(embeddings).astype("float32")
        dimension = matrix.shape[1]
        try:
            index = faiss.IndexHNSWFlat(dimension, 32)
            logger.info("Using FAISS HNSW index")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falling back to FAISS FlatL2 index: %s", exc)
            index = faiss.IndexFlatL2(dimension)
        index.add(matrix)

        faiss.write_index(index, str(self._index_path))
        logger.info("Vector index stored at %s", self._index_path)

        with self._docs_path.open("wb") as handle:
            pickle.dump(documents, handle)
        logger.info("Persisted %s document chunks", len(documents))

    def load_store(self) -> bool:
        if not self._index_path.exists() or not self._docs_path.exists():
            logger.warning("Vector store not found at %s", self._index_path.parent)
            return False

        try:
            self._index = faiss.read_index(str(self._index_path), faiss.IO_FLAG_MMAP)
            with self._docs_path.open("rb") as handle:
                self._documents = pickle.load(handle)
            logger.info("Vector store loaded: %s documents", len(self._documents))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load vector store: %s", exc)
            self._index = None
            self._documents = None
            return False

    def search(self, query: str, *, k: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self._index or not self._documents:
            logger.error("Vector store is not loaded; unable to search")
            return []

        target_k = k or self._config.top_k_results
        model = self._get_embedding_model()
        query_embedding = (
            model.encode([query], batch_size=1, show_progress_bar=False)
            .astype("float32")
        )
        search_k = min(target_k * 3, len(self._documents)) or target_k
        distances, indices = self._index.search(query_embedding, search_k)

        results: List[Dict[str, Any]] = []
        for idx, distance in zip(indices[0], distances[0]):
            if idx == -1 or idx >= len(self._documents):
                continue
            content = self._documents[idx].strip()
            if len(content) < 50:
                continue

            similarity = 1.0 / (1.0 + distance)
            query_words = set(query.lower().split())
            content_words = set(content.lower().split())
            overlap_ratio = (len(query_words & content_words) / len(query_words)) if query_words else 0.0
            boosted_score = similarity * (1 + overlap_ratio * 0.2)

            results.append(
                {
                    "content": content,
                    "score": float(distance),
                    "similarity": float(similarity),
                    "relevance": float(boosted_score),
                    "word_overlap": float(overlap_ratio),
                }
            )

        results.sort(key=lambda item: item["relevance"], reverse=True)
        filtered = [item for item in results if item["similarity"] > 0.3]
        final = (filtered or results)[:target_k]

        if final:
            logger.info(
                "Search returned %s results (best relevance %.3f)",
                len(final),
                final[0]["relevance"],
            )
        else:
            logger.warning("No results returned for query '%s'", query)
        return final
