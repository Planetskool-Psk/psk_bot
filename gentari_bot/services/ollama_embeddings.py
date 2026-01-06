"""Ollama-based embedding service for Mac compatibility."""

from collections import OrderedDict
from typing import Optional

import numpy as np
from ollama import Client

from gentari_bot.logging import get_logger

logger = get_logger(__name__)


class OllamaEmbeddings:
    """Generate embeddings using Ollama's embedding models.
    
    This approach is more stable on macOS than using sentence-transformers directly,
    as Ollama handles the low-level tensor operations and threading internally.
    Includes an LRU cache to speed up repeated queries.
    """

    def __init__(
        self,
        model_name: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        cache_size: int = 128,
    ):
        """Initialize Ollama embeddings client.
        
        Args:
            model_name: Name of the Ollama embedding model (e.g., 'nomic-embed-text')
            base_url: Ollama server URL
            cache_size: Number of embeddings to cache for speed
        """
        self.model_name = model_name
        self.client = Client(host=base_url, timeout=30)  # Faster timeout
        self._dimension: int | None = None
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_size = cache_size
        logger.info(f"Initialized Ollama embeddings with model: {model_name}")

    def _cache_key(self, text: str) -> str:
        """Normalize text for cache key."""
        return text.strip().lower()[:500]  # Limit key size

    def _get_cached(self, text: str) -> Optional[np.ndarray]:
        """Get embedding from cache if available."""
        key = self._cache_key(text)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _store_cache(self, text: str, embedding: np.ndarray) -> None:
        """Store embedding in cache."""
        key = self._cache_key(text)
        self._cache[key] = embedding
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def encode(
        self,
        sentences: list[str] | str,
        batch_size: int = 32,
        show_progress_bar: bool = False,
        normalize_embeddings: bool = True,
        **kwargs,
    ) -> np.ndarray:
        """Encode sentences into embeddings using Ollama with caching.
        
        Args:
            sentences: Single sentence or list of sentences to embed
            batch_size: Batch size for processing (ignored, kept for API compatibility)
            show_progress_bar: Whether to show progress (ignored, kept for API compatibility)
            normalize_embeddings: Whether to L2-normalize embeddings
            **kwargs: Additional arguments (ignored, kept for API compatibility)
            
        Returns:
            NumPy array of embeddings with shape (n_sentences, embedding_dim)
        """
        # Convert single string to list
        if isinstance(sentences, str):
            sentences = [sentences]
        
        embeddings = []
        for text in sentences:
            # Check cache first
            cached = self._get_cached(text)
            if cached is not None:
                embeddings.append(cached)
                continue
            
            try:
                response = self.client.embeddings(model=self.model_name, prompt=text)
                embedding = np.array(response["embedding"], dtype=np.float32)
                
                # Cache dimension on first call
                if self._dimension is None:
                    self._dimension = len(embedding)
                
                # Normalize if requested
                if normalize_embeddings:
                    norm = np.linalg.norm(embedding)
                    if norm > 0:
                        embedding = embedding / norm
                
                # Store in cache
                self._store_cache(text, embedding)
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Failed to generate embedding for text: {e}")
                # Return zero vector on error
                dim = self._dimension or 768  # Default dimension
                embeddings.append(np.zeros(dim, dtype=np.float32))
        
        return np.array(embeddings)

    def get_sentence_embedding_dimension(self) -> int:
        """Get the dimension of the embeddings.
        
        Returns:
            Embedding dimension (e.g., 768 for nomic-embed-text)
        """
        if self._dimension is None:
            # Generate a dummy embedding to get dimension
            dummy = self.encode("test")
            self._dimension = dummy.shape[1] if len(dummy.shape) > 1 else dummy.shape[0]
        return self._dimension

    def __call__(self, sentences: list[str] | str) -> np.ndarray:
        """Shorthand for encode() to match SentenceTransformer API."""
        return self.encode(sentences)
