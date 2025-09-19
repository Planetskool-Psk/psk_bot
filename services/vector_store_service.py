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
        
        # Preload the embedding model to avoid delay on first message
        log.info("Preloading embedding model during initialization...")
        self._get_embedding_model()
        log.info("Embedding model preloaded successfully")

    def _get_embedding_model(self) -> SentenceTransformer:
        """Loads the sentence transformer model (thread-safe and memory-optimized)."""
        with self.lock:
            if self.embedding_model is None:
                log.info(f"Loading embedding model: {config.EMBEDDING_MODEL_NAME}")
                # Load with memory optimizations for 8GB RAM
                self.embedding_model = SentenceTransformer(
                    config.EMBEDDING_MODEL_NAME,
                    device='cpu',  # Force CPU to avoid GPU memory issues
                    trust_remote_code=False  # Security and memory optimization
                )
                # Set to half precision if possible to save memory
                try:
                    self.embedding_model.half()
                    log.info("Enabled half-precision mode for memory efficiency")
                except:
                    log.info("Half-precision not available, using full precision")
        return self.embedding_model

    def create_and_save_store(self, chunks: List[str], batch_size: int = 32) -> None:
        """Creates a FAISS vector store from text chunks and saves it to disk. Uses smaller batching for 8GB RAM."""
        if not chunks:
            log.error("No chunks provided to create vector store.")
            return

        os.makedirs(config.VECTOR_STORE_DIR, exist_ok=True)
        log.info("Creating vector embeddings for chunks (small batches for memory efficiency)...")
        model = self._get_embedding_model()
        embeddings = []
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            batch_emb = model.encode(batch, show_progress_bar=False, batch_size=16)  # Smaller batch size
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
        """Performs an enhanced semantic search with better relevance scoring and filtering."""
        if self.index is None or self.documents is None:
            log.error("Vector store is not loaded. Cannot perform search.")
            return []

        if k is None:
            k = getattr(config, "TOP_K_RESULTS", 2)  # Increased default for better context

        model = self._get_embedding_model()
        # Use float32 for memory efficiency on 8GB RAM
        query_embedding = model.encode([query], batch_size=1, show_progress_bar=False).astype("float32")

        # Search with more candidates to filter later
        search_k = min(k * 3, len(self.documents))  # Get 3x candidates for filtering
        distances, indices = self.index.search(query_embedding, search_k)
        
        # Calculate similarity scores (lower distance = higher similarity)
        results = []
        for idx, dist in zip(indices[0], distances[0]):
            if idx < len(self.documents) and idx != -1:  # Valid index check
                # Convert distance to similarity score (0-1, higher is better)
                similarity_score = 1.0 / (1.0 + dist)
                
                content = self.documents[idx]
                
                # Basic quality filtering - skip very short or repetitive chunks
                if len(content.strip()) < 50:  # Skip very short chunks
                    continue
                    
                # Check for content relevance using simple keyword matching
                query_words = set(query.lower().split())
                content_words = set(content.lower().split())
                word_overlap = len(query_words.intersection(content_words))
                overlap_ratio = word_overlap / len(query_words) if query_words else 0
                
                # Boost score if there's good word overlap
                boosted_score = similarity_score * (1 + overlap_ratio * 0.2)
                
                results.append({
                    "content": content, 
                    "score": dist,  # Keep original distance for compatibility
                    "similarity": similarity_score,
                    "relevance": boosted_score,
                    "word_overlap": overlap_ratio
                })
        
        # Sort by relevance score (higher is better)
        results.sort(key=lambda x: x["relevance"], reverse=True)
        
        # Filter out very poor results (similarity < 0.3)
        filtered_results = [r for r in results if r["similarity"] > 0.3]
        
        # If we filtered everything, return best original results
        if not filtered_results and results:
            filtered_results = results[:k]
            log.warning(f"All results had low similarity, returning best {len(filtered_results)} anyway")
        
        # Return top k results
        final_results = filtered_results[:k]
        
        if final_results:
            best_relevance = final_results[0]["relevance"]
            avg_relevance = sum(r["relevance"] for r in final_results) / len(final_results)
            log.info(f"Search returned {len(final_results)} results. Best relevance: {best_relevance:.3f}, Avg: {avg_relevance:.3f}")
        
        return final_results
