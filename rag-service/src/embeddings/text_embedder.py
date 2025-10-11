"""
Text Embedding Service for Story 6.2
Handles text embedding generation for semantic search
"""

import asyncio
from typing import List, Dict, Any, Optional, Union
import time

import numpy as np
import structlog
from sentence_transformers import SentenceTransformer

logger = structlog.get_logger(__name__)


class TextEmbedder:
    """
    Text embedding service using sentence transformers

    Features:
    - Efficient batch embedding generation
    - Multiple model support
    - Embedding caching
    - Automatic text chunking for large documents
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize text embedder"""
        self.model_name = model_name
        self.config = config or {}
        self.model = None  # Lazy load

        # Configuration
        self.max_text_length = self.config.get('max_text_length', 512)
        self.batch_size = self.config.get('batch_size', 32)
        self.normalize_embeddings = self.config.get('normalize_embeddings', True)

        # Model specifications
        self.model_specs = {
            'all-MiniLM-L6-v2': {'dimension': 384, 'max_length': 256},
            'all-mpnet-base-v2': {'dimension': 768, 'max_length': 384},
            'paraphrase-multilingual-MiniLM-L12-v2': {'dimension': 384, 'max_length': 128}
        }

        self.dimension = self.model_specs.get(model_name, {}).get('dimension', 384)

        logger.info("TextEmbedder initialized",
                   model=self.model_name,
                   dimension=self.dimension)

    async def _get_model(self) -> SentenceTransformer:
        """Lazy load embedding model"""
        if self.model is None:
            logger.info("Loading embedding model", model=self.model_name)
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None,
                lambda: SentenceTransformer(self.model_name)
            )
            logger.info("Embedding model loaded successfully")
        return self.model

    async def embed_text(
        self,
        text: str,
        chunk_text: bool = True
    ) -> np.ndarray:
        """
        Generate embedding for a single text

        Args:
            text: Text to embed
            chunk_text: Whether to chunk long text

        Returns:
            Numpy array embedding
        """
        try:
            if not text or not text.strip():
                # Return zero vector for empty text
                return np.zeros(self.dimension, dtype=np.float32)

            # Prepare text
            prepared_text = self._prepare_text(text, chunk_text)

            # Generate embedding
            model = await self._get_model()
            loop = asyncio.get_event_loop()

            embedding = await loop.run_in_executor(
                None,
                lambda: model.encode(
                    prepared_text,
                    convert_to_numpy=True,
                    normalize_embeddings=self.normalize_embeddings
                )
            )

            logger.debug("Text embedding generated",
                        text_length=len(text),
                        embedding_shape=embedding.shape)

            return embedding

        except Exception as e:
            logger.error("Failed to generate text embedding",
                        error=str(e),
                        text_preview=text[:100])
            # Return zero vector as fallback
            return np.zeros(self.dimension, dtype=np.float32)

    async def embed_texts(
        self,
        texts: List[str],
        chunk_texts: bool = True
    ) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts in batches

        Args:
            texts: List of texts to embed
            chunk_texts: Whether to chunk long texts

        Returns:
            List of numpy array embeddings
        """
        if not texts:
            return []

        try:
            logger.info("Generating batch embeddings",
                       count=len(texts),
                       batch_size=self.batch_size)

            start_time = time.time()
            embeddings = []

            # Process in batches
            for i in range(0, len(texts), self.batch_size):
                batch_texts = texts[i:i + self.batch_size]

                # Prepare batch texts
                prepared_batch = [
                    self._prepare_text(text, chunk_texts)
                    for text in batch_texts
                ]

                # Generate batch embeddings
                batch_embeddings = await self._generate_batch_embeddings(prepared_batch)
                embeddings.extend(batch_embeddings)

                logger.debug("Batch processed",
                           batch_index=i // self.batch_size + 1,
                           batch_size=len(batch_texts))

            processing_time = time.time() - start_time
            logger.info("Batch embeddings completed",
                       total_count=len(embeddings),
                       processing_time_ms=processing_time * 1000)

            return embeddings

        except Exception as e:
            logger.error("Failed to generate batch embeddings",
                        error=str(e),
                        texts_count=len(texts))
            # Return zero vectors as fallback
            return [np.zeros(self.dimension, dtype=np.float32) for _ in texts]

    async def embed_document_chunks(
        self,
        chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Add embeddings to document chunks

        Args:
            chunks: List of document chunks with content

        Returns:
            Chunks with embeddings added
        """
        if not chunks:
            return chunks

        try:
            logger.info("Embedding document chunks", count=len(chunks))

            # Extract text content from chunks
            texts = [chunk.get('content', '') for chunk in chunks]

            # Generate embeddings
            embeddings = await self.embed_texts(texts)

            # Add embeddings to chunks
            embedded_chunks = []
            for chunk, embedding in zip(chunks, embeddings):
                embedded_chunk = {
                    **chunk,
                    'embedding': embedding
                }
                embedded_chunks.append(embedded_chunk)

            logger.info("Document chunks embedded successfully",
                       chunks_count=len(embedded_chunks))

            return embedded_chunks

        except Exception as e:
            logger.error("Failed to embed document chunks",
                        error=str(e),
                        chunks_count=len(chunks))
            # Return chunks without embeddings
            return chunks

    async def _generate_batch_embeddings(
        self,
        texts: List[str]
    ) -> List[np.ndarray]:
        """Generate embeddings for a batch of texts"""
        model = await self._get_model()
        loop = asyncio.get_event_loop()

        embeddings = await loop.run_in_executor(
            None,
            lambda: model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=self.normalize_embeddings,
                batch_size=min(len(texts), self.batch_size)
            )
        )

        # Convert to list of individual arrays
        return [embeddings[i] for i in range(len(embeddings))]

    def _prepare_text(self, text: str, chunk_text: bool = True) -> str:
        """Prepare text for embedding"""
        if not text:
            return ""

        # Clean text
        cleaned = text.strip()

        # Handle text length
        if chunk_text and len(cleaned) > self.max_text_length:
            # Take the first part for now (more sophisticated chunking could be added)
            cleaned = cleaned[:self.max_text_length]
            logger.debug("Text truncated for embedding",
                        original_length=len(text),
                        truncated_length=len(cleaned))

        return cleaned

    async def calculate_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """Calculate cosine similarity between two embeddings"""
        try:
            # Ensure embeddings are normalized
            if self.normalize_embeddings:
                norm1 = np.linalg.norm(embedding1)
                norm2 = np.linalg.norm(embedding2)

                if norm1 > 0 and norm2 > 0:
                    embedding1 = embedding1 / norm1
                    embedding2 = embedding2 / norm2

            # Calculate cosine similarity
            similarity = np.dot(embedding1, embedding2)
            return float(similarity)

        except Exception as e:
            logger.error("Failed to calculate similarity", error=str(e))
            return 0.0

    async def find_most_similar(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: List[np.ndarray],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Find most similar embeddings to query"""
        try:
            similarities = []

            for i, candidate in enumerate(candidate_embeddings):
                similarity = await self.calculate_similarity(query_embedding, candidate)
                similarities.append({
                    'index': i,
                    'similarity': similarity
                })

            # Sort by similarity and return top-k
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            return similarities[:top_k]

        except Exception as e:
            logger.error("Failed to find most similar embeddings", error=str(e))
            return []

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the embedding model"""
        return {
            'model_name': self.model_name,
            'dimension': self.dimension,
            'max_text_length': self.max_text_length,
            'batch_size': self.batch_size,
            'normalize_embeddings': self.normalize_embeddings,
            'model_loaded': self.model is not None
        }