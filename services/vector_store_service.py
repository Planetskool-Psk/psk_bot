# /rag-chatbot-ollama/services/vector_store_service.py


import os
import pickle
import faiss
from sentence_transformers import SentenceTransformer
from utils.logger import log
import config
import numpy as np
import threading
from typing import List, Optional, Any



class VectorStoreService:
    def __init__(self) -> None:
        self.index_path = os.path.join(
            config.VECTOR_STORE_DIR, f"{config.VECTOR_STORE_INDEX_NAME}.faiss"
        )
        self.docs_path = os.path.join(
            config.VECTOR_STORE_DIR, f"{config.VECTOR_STORE_INDEX_NAME}.pkl"
        )
        self.embedding_model: Optional[SentenceTransformer] = None
        self.index: Optional[Any] = None
        self.documents: Optional[List[str]] = None
        self.lock = threading.Lock()  # For thread safety

    def _get_embedding_model(self) -> SentenceTransformer:
        """Loads the sentence transformer model (thread-safe)."""
        with self.lock:
            if self.embedding_model is None:
                log.info(f"Loading embedding model: {config.EMBEDDING_MODEL_NAME}")
                self.embedding_model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
        return self.embedding_model

    def create_and_save_store(self, chunks: List[str], batch_size: int = 64) -> None:
        """Creates a FAISS vector store from text chunks and saves it to disk. Uses batching for large datasets."""
        if not chunks:
            log.error("No chunks provided to create vector store.")
            return

        os.makedirs(config.VECTOR_STORE_DIR, exist_ok=True)
        log.info("Creating vector embeddings for chunks (batched)...")
        model = self._get_embedding_model()
        embeddings = []
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            batch_emb = model.encode(batch, show_progress_bar=False)
            embeddings.append(batch_emb)
        embeddings = np.vstack(embeddings).astype("float32")

        # Create FAISS index (use HNSW for large scale, fallback to FlatL2)
        dimension = embeddings.shape[1]
        try:
            index = faiss.IndexHNSWFlat(dimension, 32)
            log.info("Using FAISS HNSW index for fast ANN search.")
        except Exception as e:
            log.warning(f"HNSW not available, using FlatL2. Reason: {e}")
            index = faiss.IndexFlatL2(dimension)
        index.add(embeddings)

        log.info(f"Saving FAISS index to {self.index_path}")
        faiss.write_index(index, self.index_path)

        log.info(f"Saving document chunks to {self.docs_path}")
        with open(self.docs_path, "wb") as f:
            pickle.dump(chunks, f)

    def load_store(self) -> bool:
        """Loads the FAISS index and documents from disk. Uses memory-mapping for large indexes."""
        if os.path.exists(self.index_path) and os.path.exists(self.docs_path):
            log.info("Loading vector store from disk...")
            try:
                self.index = faiss.read_index(self.index_path, faiss.IO_FLAG_MMAP)
                with open(self.docs_path, "rb") as f:
                    self.documents = pickle.load(f)
                log.info("Vector store loaded successfully.")
                return True
            except Exception as e:
                log.error(f"Failed to load vector store: {e}")
                return False
        else:
            log.warning("Vector store not found on disk.")
            return False

    def search(self, query: str, k: int = None) -> List[dict]:
        """Performs a semantic search on the vector store. Returns top-k documents with scores."""
        if self.index is None or self.documents is None:
            log.error("Vector store is not loaded. Cannot perform search.")
            return []

        if k is None:
            k = getattr(config, "TOP_K_RESULTS", 5)

        model = self._get_embedding_model()
        query_embedding = model.encode([query]).astype("float32")

        distances, indices = self.index.search(query_embedding, k)
        results = []
        for idx, dist in zip(indices[0], distances[0]):
            if idx < len(self.documents):
                results.append({"content": self.documents[idx], "score": float(dist)})
        return results

        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1:  # FAISS returns -1 for no result
                results.append(
                    {"content": self.documents[idx], "score": distances[0][i]}
                )
                print()
        return results
