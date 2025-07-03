# /rag-chatbot-ollama/services/vector_store_service.py

import os
import pickle
import faiss
from sentence_transformers import SentenceTransformer
from utils.logger import log
import config
import numpy as np


class VectorStoreService:
    def __init__(self):
        self.index_path = os.path.join(
            config.VECTOR_STORE_DIR, f"{config.VECTOR_STORE_INDEX_NAME}.faiss"
        )
        self.docs_path = os.path.join(
            config.VECTOR_STORE_DIR, f"{config.VECTOR_STORE_INDEX_NAME}.pkl"
        )
        self.embedding_model = None
        self.index = None
        self.documents = None

    def _get_embedding_model(self):
        """Loads the sentence transformer model."""
        if self.embedding_model is None:
            log.info(f"Loading embedding model: {config.EMBEDDING_MODEL_NAME}")
            self.embedding_model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
        return self.embedding_model

    def create_and_save_store(self, chunks):
        """Creates a FAISS vector store from text chunks and saves it to disk."""
        if not chunks:
            log.error("No chunks provided to create vector store.")
            return

        os.makedirs(config.VECTOR_STORE_DIR, exist_ok=True)
        log.info("Creating vector embeddings for chunks...")
        model = self._get_embedding_model()
        embeddings = model.encode(chunks, show_progress_bar=True)

        # FAISS requires float32
        embeddings = np.array(embeddings).astype("float32")

        # Create FAISS index
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings)

        log.info(f"Saving FAISS index to {self.index_path}")
        faiss.write_index(index, self.index_path)

        log.info(f"Saving document chunks to {self.docs_path}")
        with open(self.docs_path, "wb") as f:
            pickle.dump(chunks, f)

    def load_store(self):
        """Loads the FAISS index and documents from disk."""
        if os.path.exists(self.index_path) and os.path.exists(self.docs_path):
            log.info("Loading vector store from disk...")
            self.index = faiss.read_index(self.index_path)
            with open(self.docs_path, "rb") as f:
                self.documents = pickle.load(f)
            log.info("Vector store loaded successfully.")
            return True
        else:
            log.warning("Vector store not found on disk.")
            return False

    def search(self, query, k=config.TOP_K_RESULTS):
        """Performs a semantic search on the vector store."""
        if self.index is None or self.documents is None:
            log.error("Vector store is not loaded. Cannot perform search.")
            return []

        model = self._get_embedding_model()
        query_embedding = model.encode([query]).astype("float32")

        distances, indices = self.index.search(query_embedding, k)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1:  # FAISS returns -1 for no result
                results.append(
                    {"content": self.documents[idx], "score": distances[0][i]}
                )
                print()
        return results
