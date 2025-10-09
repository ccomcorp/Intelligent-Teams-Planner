"""
Fallback embeddings generator for testing without sentence-transformers
Story 6.2 Task 2: Basic embeddings for testing
"""

import asyncio
import hashlib
from typing import List, Dict, Any, Optional
import time

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class EmbeddingGenerator:
    """
    Fallback embedding generator using simple text hashing for testing
    """

    def __init__(
        self,
        model_name: str = "fallback-hash-embeddings",
        cache_size: int = 10000,
        batch_size: int = 32
    ):
        self.model_name = model_name
        self.cache_size = cache_size
        self.batch_size = batch_size
        self.dimension = 768  # Match expected dimension

        # Simple cache
        self.cache = {}

        # Performance tracking
        self.embedding_count = 0
        self.total_processing_time = 0.0

        logger.info("EmbeddingGenerator (fallback) initialized",
                   model=model_name,
                   dimension=self.dimension,
                   cache_size=cache_size)

    async def initialize(self) -> None:
        """Initialize the embedding model (no-op for fallback)"""
        logger.info("EmbeddingGenerator (fallback) initialized - ready")

    async def generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate a simple hash-based embedding for testing
        """
        if not text or not text.strip():
            return np.zeros(self.dimension, dtype=np.float32)

        try:
            start_time = time.time()

            # Check cache
            text_hash = hashlib.md5(text.encode()).hexdigest()
            if text_hash in self.cache:
                return self.cache[text_hash]

            # Generate simple hash-based embedding
            # This is just for testing - not a real embedding
            embedding = self._hash_to_embedding(text)

            # Cache result
            if len(self.cache) < self.cache_size:
                self.cache[text_hash] = embedding

            # Update metrics
            processing_time = time.time() - start_time
            self.embedding_count += 1
            self.total_processing_time += processing_time

            logger.debug("Generated embedding (fallback)",
                        text_length=len(text),
                        dimension=embedding.shape[0],
                        processing_time=f"{processing_time:.3f}s")

            return embedding

        except Exception as e:
            logger.error("Failed to generate embedding (fallback)", error=str(e))
            raise

    def _hash_to_embedding(self, text: str) -> np.ndarray:
        """Convert text to a deterministic pseudo-embedding using hashing"""
        # Create multiple hashes to fill the 768 dimensions
        hash_input = text.lower().strip()

        # Generate enough hash values to fill 768 dimensions
        embeddings = []
        for i in range(0, self.dimension, 16):  # MD5 hash gives 16 bytes
            hash_obj = hashlib.md5(f"{hash_input}_{i}".encode())
            hash_bytes = hash_obj.digest()

            # Convert bytes to floats in range [-1, 1]
            for byte in hash_bytes:
                if len(embeddings) < self.dimension:
                    # Normalize byte (0-255) to range [-1, 1]
                    normalized = (byte / 127.5) - 1.0
                    embeddings.append(normalized)

        # Ensure exactly the right dimension
        embedding_array = np.array(embeddings[:self.dimension], dtype=np.float32)

        # Normalize to unit vector (for cosine similarity)
        norm = np.linalg.norm(embedding_array)
        if norm > 0:
            embedding_array = embedding_array / norm

        return embedding_array

    async def generate_embeddings_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for multiple texts"""
        embeddings = []
        for text in texts:
            embedding = await self.generate_embedding(text)
            embeddings.append(embedding)

        logger.info("Generated batch embeddings (fallback)",
                   batch_size=len(texts))

        return embeddings

    async def compute_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        method: str = "cosine"
    ) -> float:
        """Compute similarity between two embeddings"""
        try:
            if method == "cosine":
                dot_product = np.dot(embedding1, embedding2)
                norm1 = np.linalg.norm(embedding1)
                norm2 = np.linalg.norm(embedding2)

                if norm1 == 0 or norm2 == 0:
                    return 0.0

                return float(dot_product / (norm1 * norm2))
            else:
                return float(np.dot(embedding1, embedding2))

        except Exception as e:
            logger.error("Failed to compute similarity (fallback)", error=str(e))
            return 0.0

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
            "cache_size": len(self.cache)
        }

    async def health_check(self) -> str:
        """Check embedding model health"""
        try:
            test_embedding = await self.generate_embedding("Health check test")
            if test_embedding.shape[0] != self.dimension:
                return "degraded"
            return "healthy"
        except Exception as e:
            logger.error("Embedding health check failed (fallback)", error=str(e))
            return "unhealthy"

    def clear_cache(self) -> None:
        """Clear the embedding cache"""
        self.cache.clear()
        logger.info("Embedding cache cleared (fallback)")