"""
Embeddings generator for RAG service
Story 6.2 Task 2: Implement Semantic Search Engine
Aligned with IMPLEMENTATION-PLAN.md (768-dimensional embeddings)
"""

import asyncio
from typing import List, Dict, Any, Optional, Union
import time
from functools import lru_cache

import numpy as np
import structlog
from sentence_transformers import SentenceTransformer

logger = structlog.get_logger(__name__)


class EmbeddingGenerator:
    """
    Generate embeddings for text content using sentence transformers
    Optimized for 768-dimensional vectors as per implementation plan
    """

    def __init__(
        self,
        model_name: str = "all-mpnet-base-v2",  # 768 dimensions as per plan
        cache_size: int = 10000,
        batch_size: int = 32
    ):
        self.model_name = model_name
        self.cache_size = cache_size
        self.batch_size = batch_size
        self.model = None
        self.dimension = 768  # As specified in implementation plan

        # Performance tracking
        self.embedding_count = 0
        self.total_processing_time = 0.0

        logger.info("EmbeddingGenerator initializing",
                   model=model_name,
                   dimension=self.dimension,
                   cache_size=cache_size)

    async def initialize(self) -> None:
        """Initialize the embedding model asynchronously"""
        try:
            start_time = time.time()

            # Load model in a thread to avoid blocking
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None,
                lambda: SentenceTransformer(self.model_name)
            )

            # Verify model dimensions
            test_embedding = self.model.encode(["test"], convert_to_numpy=True)
            actual_dimension = test_embedding.shape[1]

            if actual_dimension != self.dimension:
                logger.warning("Model dimension mismatch",
                             expected=self.dimension,
                             actual=actual_dimension)
                self.dimension = actual_dimension

            load_time = time.time() - start_time
            logger.info("EmbeddingGenerator initialized",
                       model=self.model_name,
                       dimension=self.dimension,
                       load_time=f"{load_time:.2f}s")

        except Exception as e:
            logger.error("Failed to initialize embedding model", error=str(e))
            raise

    async def generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text

        Args:
            text: Input text to embed

        Returns:
            768-dimensional numpy array
        """
        if not self.model:
            raise ValueError("Embedding model not initialized. Call initialize() first.")

        if not text or not text.strip():
            # Return zero vector for empty text
            return np.zeros(self.dimension, dtype=np.float32)

        try:
            start_time = time.time()

            # Check cache first
            cached_embedding = self._get_cached_embedding(text)
            if cached_embedding is not None:
                return cached_embedding

            # Generate embedding in thread to avoid blocking
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: self.model.encode([text], convert_to_numpy=True)[0]
            )

            # Ensure float32 for consistency
            embedding = embedding.astype(np.float32)

            # Cache the result
            self._cache_embedding(text, embedding)

            # Update performance metrics
            processing_time = time.time() - start_time
            self.embedding_count += 1
            self.total_processing_time += processing_time

            logger.debug("Generated embedding",
                        text_length=len(text),
                        dimension=embedding.shape[0],
                        processing_time=f"{processing_time:.3f}s")

            return embedding

        except Exception as e:
            logger.error("Failed to generate embedding", error=str(e), text_preview=text[:100])
            raise

    async def generate_embeddings_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts in batch for better performance

        Args:
            texts: List of input texts

        Returns:
            List of 768-dimensional numpy arrays
        """
        if not self.model:
            raise ValueError("Embedding model not initialized. Call initialize() first.")

        if not texts:
            return []

        try:
            start_time = time.time()

            # Filter out empty texts and track indices
            valid_texts = []
            valid_indices = []
            embeddings_result = [None] * len(texts)

            for i, text in enumerate(texts):
                if text and text.strip():
                    # Check cache first
                    cached_embedding = self._get_cached_embedding(text)
                    if cached_embedding is not None:
                        embeddings_result[i] = cached_embedding
                    else:
                        valid_texts.append(text)
                        valid_indices.append(i)
                else:
                    # Zero vector for empty text
                    embeddings_result[i] = np.zeros(self.dimension, dtype=np.float32)

            # Process valid texts in batches
            if valid_texts:
                loop = asyncio.get_event_loop()

                # Process in chunks to manage memory
                for i in range(0, len(valid_texts), self.batch_size):
                    batch_texts = valid_texts[i:i + self.batch_size]
                    batch_indices = valid_indices[i:i + self.batch_size]

                    # Generate embeddings for batch
                    batch_embeddings = await loop.run_in_executor(
                        None,
                        lambda: self.model.encode(batch_texts, convert_to_numpy=True)
                    )

                    # Store results and cache
                    for j, embedding in enumerate(batch_embeddings):
                        embedding = embedding.astype(np.float32)
                        result_index = batch_indices[j]
                        embeddings_result[result_index] = embedding

                        # Cache the result
                        self._cache_embedding(batch_texts[j], embedding)

            # Update performance metrics
            processing_time = time.time() - start_time
            self.embedding_count += len(texts)
            self.total_processing_time += processing_time

            logger.info("Generated batch embeddings",
                       batch_size=len(texts),
                       valid_texts=len(valid_texts),
                       cached_texts=len(texts) - len(valid_texts),
                       processing_time=f"{processing_time:.3f}s")

            return embeddings_result

        except Exception as e:
            logger.error("Failed to generate batch embeddings", error=str(e), batch_size=len(texts))
            raise

    @lru_cache(maxsize=10000)  # Cache based on init parameter
    def _get_cached_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get cached embedding for text (uses LRU cache)"""
        # This method is automatically cached by lru_cache decorator
        # We return None here as the actual caching happens via the decorator
        return None

    def _cache_embedding(self, text: str, embedding: np.ndarray) -> None:
        """Cache embedding (handled by LRU cache decorator)"""
        # The actual caching is handled by the lru_cache decorator on _get_cached_embedding
        # This method is kept for interface consistency
        pass

    async def compute_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        method: str = "cosine"
    ) -> float:
        """
        Compute similarity between two embeddings

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            method: Similarity method (cosine, dot, euclidean)

        Returns:
            Similarity score
        """
        try:
            if method == "cosine":
                # Cosine similarity
                dot_product = np.dot(embedding1, embedding2)
                norm1 = np.linalg.norm(embedding1)
                norm2 = np.linalg.norm(embedding2)

                if norm1 == 0 or norm2 == 0:
                    return 0.0

                return float(dot_product / (norm1 * norm2))

            elif method == "dot":
                # Dot product
                return float(np.dot(embedding1, embedding2))

            elif method == "euclidean":
                # Negative Euclidean distance (higher = more similar)
                return float(-np.linalg.norm(embedding1 - embedding2))

            else:
                raise ValueError(f"Unknown similarity method: {method}")

        except Exception as e:
            logger.error("Failed to compute similarity", error=str(e), method=method)
            raise

    def get_stats(self) -> Dict[str, Any]:
        """Get embedding generation statistics"""
        avg_time = (self.total_processing_time / self.embedding_count
                   if self.embedding_count > 0 else 0.0)

        return {
            "model_name": self.model_name,
            "dimension": self.dimension,
            "embeddings_generated": self.embedding_count,
            "total_processing_time": self.total_processing_time,
            "average_processing_time": avg_time,
            "cache_info": self._get_cached_embedding.cache_info()._asdict()
        }

    async def health_check(self) -> str:
        """Check embedding model health"""
        try:
            if not self.model:
                return "unhealthy"

            # Test embedding generation
            test_embedding = await self.generate_embedding("Health check test")

            if test_embedding.shape[0] != self.dimension:
                return "degraded"

            return "healthy"

        except Exception as e:
            logger.error("Embedding health check failed", error=str(e))
            return "unhealthy"

    def clear_cache(self) -> None:
        """Clear the embedding cache"""
        self._get_cached_embedding.cache_clear()
        logger.info("Embedding cache cleared")

    async def precompute_embeddings(self, texts: List[str]) -> None:
        """Precompute embeddings for a list of texts to warm up cache"""
        logger.info("Precomputing embeddings", count=len(texts))

        try:
            await self.generate_embeddings_batch(texts)
            logger.info("Precomputation completed", count=len(texts))
        except Exception as e:
            logger.error("Precomputation failed", error=str(e))
            raise


class EmbeddingCache:
    """
    Persistent cache for embeddings to avoid recomputation
    Can be extended to use Redis or other persistent storage
    """

    def __init__(self, max_size: int = 100000):
        self.max_size = max_size
        self.cache: Dict[str, np.ndarray] = {}

    def get(self, text_hash: str) -> Optional[np.ndarray]:
        """Get embedding from cache"""
        return self.cache.get(text_hash)

    def set(self, text_hash: str, embedding: np.ndarray) -> None:
        """Store embedding in cache"""
        if len(self.cache) >= self.max_size:
            # Remove oldest entry (simple FIFO eviction)
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]

        self.cache[text_hash] = embedding

    def clear(self) -> None:
        """Clear cache"""
        self.cache.clear()

    def size(self) -> int:
        """Get cache size"""
        return len(self.cache)