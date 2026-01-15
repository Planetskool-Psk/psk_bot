"""Vector store management backed by FAISS."""

import json
import os
import pickle
import time
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional

os.environ.setdefault("FAISS_DISABLE_GPU", "1")

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from gentari_bot.logging import get_logger
from gentari_bot.services.ollama_embeddings import OllamaEmbeddings
from gentari_bot.settings import AppSettings, settings

logger = get_logger(__name__)


class VectorStoreService:
    """Coordinate embedding generation, persistence, and semantic search."""

    def __init__(self, *, config: AppSettings = settings, doc_id: str = None) -> None:
        self._config = config
        self._doc_id = doc_id  # None means default/legacy index
        self._lock = Lock()
        self._embedding_model: Optional[SentenceTransformer | OllamaEmbeddings] = None
        self._use_ollama = config.embedding_model_name.startswith("nomic-embed-text")
        self._index: Optional[Any] = None
        self._documents: Optional[List[str]] = None
        self._metric: str = "ip"
        self._query_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_limit = 32

        # Set paths based on doc_id
        base_path = Path(self._config.vector_store_dir).parent
        if doc_id:
            # Per-document index
            index_dir = base_path / doc_id
        else:
            # Default legacy index
            index_dir = base_path / "faiss_index"
        
        index_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = index_dir / "faiss_index.faiss"
        self._docs_path = index_dir / "faiss_index.pkl"
        self._meta_path = index_dir / "faiss_index.meta.json"

        logger.info("Preloading embedding model: %s", self._config.embedding_model_name)
        self._get_embedding_model()
    
    @classmethod
    def for_document(cls, doc_id: str, config: AppSettings = settings) -> "VectorStoreService":
        """Factory method to create a vector store for a specific document."""
        return cls(config=config, doc_id=doc_id)

    def _ensure_store_directory(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_embedding_model(self) -> SentenceTransformer | OllamaEmbeddings:
        with self._lock:
            if self._embedding_model is None:
                if self._use_ollama:
                    # Use Ollama for Mac-compatible nomic-embed-text
                    self._embedding_model = OllamaEmbeddings(
                        model_name=self._config.embedding_model_name,
                        base_url=self._config.ollama_base_url,
                    )
                    logger.info("Using Ollama embeddings (Mac-compatible)")
                else:
                    # Use sentence-transformers for other models
                    import torch
                    torch.set_num_threads(1)
                    torch.set_num_interop_threads(1)
                    
                    self._embedding_model = SentenceTransformer(
                        self._config.embedding_model_name,
                        device="cpu",
                        trust_remote_code=True,
                    )
                    logger.info("Embedding model loaded in full precision with threading disabled")
        return self._embedding_model

    def _write_metadata(self, *, dimension: int, count: int) -> None:
        metadata = {
            "embedding_model": self._config.embedding_model_name,
            "dimension": dimension,
            "metric": self._metric,
            "document_count": count,
            "created_at": int(time.time()),
        }
        with self._meta_path.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle)
        logger.info("Persisted vector store metadata at %s", self._meta_path)

    def _load_metadata(self) -> None:
        if not self._meta_path.exists():
            logger.warning("Vector store metadata missing at %s", self._meta_path)
            return
        try:
            with self._meta_path.open("r", encoding="utf-8") as handle:
                metadata = json.load(handle)
            self._metric = metadata.get("metric", "l2")
            expected_model = metadata.get("embedding_model")
            if expected_model and expected_model != self._config.embedding_model_name:
                logger.warning(
                    "Vector store built with %s, current embedding model is %s. Regenerate the index for best quality.",
                    expected_model,
                    self._config.embedding_model_name,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load metadata: %s", exc)

    def _cache_query_embedding(self, query: str, embedding: np.ndarray) -> None:
        key = query.strip().lower()
        self._query_cache[key] = embedding
        if len(self._query_cache) > self._cache_limit:
            self._query_cache.popitem(last=False)

    def _get_query_embedding(self, query: str) -> np.ndarray:
        key = query.strip().lower()
        if key in self._query_cache:
            self._query_cache.move_to_end(key)
            return self._query_cache[key]

        model = self._get_embedding_model()
        vector = model.encode(
            [query],
            batch_size=1,
            show_progress_bar=False,
            normalize_embeddings=True,
            device="cpu",
            convert_to_numpy=True,
        ).astype("float32")
        self._cache_query_embedding(key, vector)
        return vector

    def create_and_save_store(self, chunks: Iterable[str], *, batch_size: Optional[int] = None) -> None:
        documents = [chunk.strip() for chunk in chunks if chunk and chunk.strip()]
        if not documents:
            logger.error("No chunks provided to create vector store")
            return

        model = self._get_embedding_model()
        embeddings: List[np.ndarray] = []
        chosen_batch_size = batch_size or self._config.embedding_batch_size
        for start in range(0, len(documents), chosen_batch_size):
            batch = documents[start : start + chosen_batch_size]
            batch_embeddings = model.encode(
                batch,
                show_progress_bar=False,
                batch_size=chosen_batch_size,
                normalize_embeddings=True,
                device="cpu",
                convert_to_numpy=True,
            )
            embeddings.append(batch_embeddings)

        matrix = np.vstack(embeddings).astype("float32")
        dimension = matrix.shape[1]

        try:
            index = faiss.IndexHNSWFlat(dimension, 32, faiss.METRIC_INNER_PRODUCT)
            self._metric = "ip"
            logger.info("Using FAISS HNSW index with inner product similarity")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falling back to FAISS FlatIP index: %s", exc)
            try:
                index = faiss.IndexFlatIP(dimension)
                self._metric = "ip"
            except Exception as inner_exc:  # noqa: BLE001
                logger.warning("FlatIP unavailable, reverting to FlatL2: %s", inner_exc)
                index = faiss.IndexFlatL2(dimension)
                self._metric = "l2"

        index.add(matrix)

        faiss.write_index(index, str(self._index_path))
        logger.info("Vector index stored at %s", self._index_path)

        with self._docs_path.open("wb") as handle:
            pickle.dump(documents, handle)
        logger.info("Persisted %s document chunks", len(documents))

        self._write_metadata(dimension=dimension, count=len(documents))

    def load_store(self) -> bool:
        if not self._index_path.exists() or not self._docs_path.exists():
            logger.warning("Vector store not found at %s", self._index_path.parent)
            return False

        try:
            self._load_metadata()
            self._index = faiss.read_index(str(self._index_path), faiss.IO_FLAG_MMAP)
            if hasattr(self._index, "metric_type"):
                try:
                    metric_type = self._index.metric_type
                    self._metric = "ip" if metric_type == faiss.METRIC_INNER_PRODUCT else "l2"
                except Exception:  # noqa: BLE001
                    logger.debug("Unable to introspect FAISS metric type; using metadata default")
            with self._docs_path.open("rb") as handle:
                self._documents = pickle.load(handle)
            logger.info("Vector store loaded: %s documents", len(self._documents))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load vector store: %s", exc)
            self._index = None
            self._documents = None
            return False

    def ensure_ready(self) -> bool:
        """Idempotently load the store if it is not already ready."""
        if self._index is not None and self._documents is not None:
            return True
        return self.load_store()

    def search(self, query: str, *, k: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self.ensure_ready():
            logger.error("Vector store is not loaded; unable to search")
            return []

        if not self._index or not self._documents:
            logger.error("Vector store not initialised correctly")
            return []

        target_k = k or self._config.top_k_results
        query_embedding = self._get_query_embedding(query)
        search_k = min(target_k * 3, len(self._documents)) or target_k
        distances, indices = self._index.search(query_embedding, search_k)

        results: List[Dict[str, Any]] = []
        for idx, distance in zip(indices[0], distances[0]):
            if idx == -1 or idx >= len(self._documents):
                continue
            content = self._documents[idx].strip()
            if len(content) < 50:
                continue

            if self._metric == "ip":
                similarity = float(distance)
            else:
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

    def add_documents(self, documents: List[Dict[str, Any]], *, batch_size: Optional[int] = None) -> None:
        """
        Add documents to the vector store (used for per-document ingestion).
        
        Args:
            documents: List of dicts with 'content' key
            batch_size: Optional batch size for embedding
        """
        chunks = [doc.get("content", "").strip() for doc in documents if doc.get("content")]
        if not chunks:
            logger.error("No valid documents provided")
            return
        
        self.create_and_save_store(chunks, batch_size=batch_size)
        logger.info("Added %d documents to vector store (doc_id=%s)", len(chunks), self._doc_id)
