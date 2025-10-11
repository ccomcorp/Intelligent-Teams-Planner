"""
Vector Store implementation using pgvector
Story 6.2 Task 1: Deploy Vector Database Infrastructure
"""

import uuid
import asyncio
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

import asyncpg
import numpy as np
import structlog

from .postgres_client import PostgresClient

logger = structlog.get_logger(__name__)


class VectorStore:
    """
    Vector database implementation using PostgreSQL with pgvector extension
    Provides high-performance vector storage and similarity search
    """

    def __init__(self, postgres_client: PostgresClient, dimension: int = 768):
        self.postgres_client = postgres_client
        self.dimension = dimension
        self.pool = None

    async def initialize(self) -> None:
        """Initialize vector store with required tables and indexes"""
        try:
            # Get connection pool
            self.pool = self.postgres_client.pool

            # Create pgvector extension if not exists
            await self._create_extension()

            # Create vector tables
            await self._create_tables()

            # Create indexes for performance
            await self._create_indexes()

            logger.info("Vector store initialized successfully", dimension=self.dimension)

        except Exception as e:
            logger.error("Failed to initialize vector store", error=str(e))
            raise

    async def _create_extension(self) -> None:
        """Create pgvector extension"""
        async with self.pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            logger.debug("pgvector extension created")

    async def _create_tables(self) -> None:
        """Create vector storage tables"""
        async with self.pool.acquire() as conn:
            # Documents table (aligned with IMPLEMENTATION-PLAN.md)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    filename VARCHAR(255) NOT NULL,
                    source VARCHAR(50) NOT NULL,
                    source_id VARCHAR(255),
                    uploaded_by VARCHAR(255),
                    uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    content_type VARCHAR(100),
                    file_size INTEGER,
                    task_id VARCHAR(255),
                    task_title VARCHAR(500),
                    conversation_id VARCHAR(255),
                    metadata JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)

            # Document chunks table with vectors (aligned with IMPLEMENTATION-PLAN.md)
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector({self.dimension}),
                    metadata JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE(document_id, chunk_index)
                )
            """)

            # Search analytics table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS search_analytics (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    query TEXT NOT NULL,
                    user_id VARCHAR(100) NOT NULL,
                    results_count INTEGER NOT NULL,
                    processing_time_ms FLOAT NOT NULL,
                    filters JSONB DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            logger.debug("Vector store tables created")

    async def _create_indexes(self) -> None:
        """Create performance indexes"""
        async with self.pool.acquire() as conn:
            # Vector similarity index (IVFFLAT as per implementation plan)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_ivfflat
                ON document_chunks USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)

            # Document lookup indexes (aligned with IMPLEMENTATION-PLAN.md)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_source
                ON documents(source)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_task_id
                ON documents(task_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by
                ON documents(uploaded_by)
            """)

            # Chunk lookup indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
                ON document_chunks(document_id)
            """)

            logger.debug("Vector store indexes created")

    async def store_document(self, processed_doc: Dict[str, Any]) -> int:
        """
        Store processed document and its chunks in vector database

        Args:
            processed_doc: Document with chunks and embeddings

        Returns:
            Number of chunks stored
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Insert document record (aligned with multi-source schema)
                    document_id = await conn.fetchval("""
                        INSERT INTO documents (id, filename, source, source_id, uploaded_by, content_type, file_size, task_id, task_title, conversation_id, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        RETURNING id
                    """,
                    processed_doc["document_id"],
                    processed_doc["filename"],
                    processed_doc.get("source", "openwebui"),
                    processed_doc.get("source_id"),
                    processed_doc.get("uploaded_by", processed_doc.get("user_id")),
                    processed_doc.get("content_type", "application/octet-stream"),
                    processed_doc["file_size"],
                    processed_doc.get("task_id"),
                    processed_doc.get("task_title"),
                    processed_doc.get("conversation_id"),
                    json.dumps(processed_doc.get("metadata", {}))
                    )

                    # Insert document chunks with embeddings
                    chunks_inserted = 0
                    for i, chunk in enumerate(processed_doc["chunks"]):
                        await conn.execute("""
                            INSERT INTO document_chunks (document_id, chunk_index, content, embedding, metadata)
                            VALUES ($1, $2, $3, $4, $5)
                        """,
                        document_id,
                        i,
                        chunk["content"],
                        chunk["embedding"],
                        json.dumps(chunk.get("metadata", {}))
                        )
                        chunks_inserted += 1

                    logger.info("Document stored successfully",
                               document_id=document_id,
                               chunks=chunks_inserted)

                    return chunks_inserted

        except Exception as e:
            logger.error("Failed to store document", error=str(e))
            raise

    async def similarity_search(
        self,
        query_embedding: np.ndarray,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        similarity_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search

        Args:
            query_embedding: Query vector
            limit: Maximum results to return
            filters: Optional filters for search
            similarity_threshold: Minimum similarity score

        Returns:
            List of similar document chunks with metadata
        """
        try:
            # Convert numpy array to list for PostgreSQL
            query_vector = query_embedding.tolist()

            async with self.pool.acquire() as conn:
                # Build query with optional filters
                where_clause = "WHERE 1 = 1"
                params = [query_vector, similarity_threshold, limit]
                param_idx = 4

                if filters:
                    if "user_id" in filters:
                        where_clause += f" AND d.uploaded_by = ${param_idx}"
                        params.append(filters["user_id"])
                        param_idx += 1

                    if "document_id" in filters:
                        where_clause += f" AND c.document_id = ${param_idx}"
                        params.append(filters["document_id"])
                        param_idx += 1

                # Convert similarity threshold to distance (pgvector uses distance, not similarity)
                distance_threshold = 1 - similarity_threshold

                query = f"""
                    SELECT
                        c.id as chunk_id,
                        c.document_id,
                        c.content,
                        c.metadata as chunk_metadata,
                        c.chunk_index,
                        d.filename,
                        d.source,
                        d.task_id,
                        d.task_title,
                        d.metadata as document_metadata,
                        1 - (c.embedding <=> $1) as similarity_score
                    FROM document_chunks c
                    JOIN documents d ON c.document_id = d.id
                    {where_clause}
                    AND c.embedding <=> $1 <= $2
                    ORDER BY c.embedding <=> $1
                    LIMIT $3
                """

                # Update params to use distance threshold instead of similarity threshold
                params[1] = distance_threshold

                results = await conn.fetch(query, *params)

                # Convert to list of dictionaries
                search_results = []
                for row in results:
                    result = {
                        "chunk_id": str(row["chunk_id"]),
                        "document_id": str(row["document_id"]),
                        "content": row["content"],
                        "filename": row["filename"],
                        "source": row["source"],
                        "task_id": row["task_id"],
                        "task_title": row["task_title"],
                        "chunk_index": row["chunk_index"],
                        "chunk_metadata": row["chunk_metadata"],
                        "document_metadata": row["document_metadata"],
                        "similarity_score": float(row["similarity_score"])
                    }
                    search_results.append(result)

                logger.debug("Similarity search completed",
                           results=len(search_results),
                           threshold=similarity_threshold)

                return search_results

        except Exception as e:
            logger.error("Similarity search failed", error=str(e))
            raise

    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID with all chunks"""
        try:
            async with self.pool.acquire() as conn:
                # Get document metadata
                document = await conn.fetchrow("""
                    SELECT id, filename, source, source_id, uploaded_by, file_size, content_type, task_id, task_title, conversation_id, metadata, created_at
                    FROM documents
                    WHERE id = $1
                """, uuid.UUID(document_id))

                if not document:
                    return None

                # Get document chunks
                chunks = await conn.fetch("""
                    SELECT id, chunk_index, content, metadata
                    FROM document_chunks
                    WHERE document_id = $1
                    ORDER BY chunk_index
                """, uuid.UUID(document_id))

                return {
                    "document_id": str(document["id"]),
                    "filename": document["filename"],
                    "source": document["source"],
                    "source_id": document["source_id"],
                    "uploaded_by": document["uploaded_by"],
                    "file_size": document["file_size"],
                    "content_type": document["content_type"],
                    "task_id": document["task_id"],
                    "task_title": document["task_title"],
                    "conversation_id": document["conversation_id"],
                    "metadata": document["metadata"],
                    "created_at": document["created_at"].isoformat(),
                    "chunks": [
                        {
                            "chunk_id": str(chunk["id"]),
                            "chunk_index": chunk["chunk_index"],
                            "content": chunk["content"],
                            "metadata": chunk["metadata"]
                        }
                        for chunk in chunks
                    ]
                }

        except Exception as e:
            logger.error("Failed to get document", error=str(e), document_id=document_id)
            raise

    async def list_documents(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List user's documents"""
        try:
            async with self.pool.acquire() as conn:
                documents = await conn.fetch("""
                    SELECT
                        id,
                        filename,
                        source,
                        task_id,
                        task_title,
                        file_size,
                        content_type,
                        metadata,
                        created_at,
                        (SELECT COUNT(*) FROM document_chunks WHERE document_id = d.id) as chunk_count
                    FROM documents d
                    WHERE uploaded_by = $1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                """, user_id, limit, offset)

                return [
                    {
                        "document_id": str(doc["id"]),
                        "filename": doc["filename"],
                        "source": doc["source"],
                        "task_id": doc["task_id"],
                        "task_title": doc["task_title"],
                        "file_size": doc["file_size"],
                        "content_type": doc["content_type"],
                        "metadata": doc["metadata"],
                        "created_at": doc["created_at"].isoformat(),
                        "chunk_count": doc["chunk_count"]
                    }
                    for doc in documents
                ]

        except Exception as e:
            logger.error("Failed to list documents", error=str(e), user_id=user_id)
            raise

    async def delete_document(self, document_id: str) -> bool:
        """Delete document and all its chunks"""
        try:
            async with self.pool.acquire() as conn:
                # Delete document (chunks will be deleted via CASCADE)
                result = await conn.execute("""
                    DELETE FROM documents WHERE id = $1
                """, uuid.UUID(document_id))

                deleted = result.split()[-1] == "1"

                if deleted:
                    logger.info("Document deleted successfully", document_id=document_id)

                return deleted

        except Exception as e:
            logger.error("Failed to delete document", error=str(e), document_id=document_id)
            raise

    async def log_search_analytics(
        self,
        query: str,
        user_id: str,
        results_count: int,
        processing_time_ms: float,
        filters: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log search analytics for optimization"""
        try:
            async with self.pool.acquire() as conn:
                # Ensure user_id is a string, not a dict
                if isinstance(user_id, dict):
                    user_id = user_id.get('user_id', 'unknown')

                # Convert filters dict to JSON string for storage
                filters_json = json.dumps(filters or {})
                await conn.execute("""
                    INSERT INTO search_analytics (query, user_id, results_count, processing_time_ms, filters)
                    VALUES ($1, $2, $3, $4, $5)
                """, query, str(user_id), results_count, processing_time_ms, filters_json)

        except Exception as e:
            logger.warning("Failed to log search analytics", error=str(e))
            # Don't raise - analytics logging shouldn't break search

    async def health_check(self) -> str:
        """Check vector store health"""
        try:
            async with self.pool.acquire() as conn:
                # Test basic connectivity
                await conn.fetchval("SELECT 1")

                # Test vector extension
                await conn.fetchval("SELECT version() FROM pg_extension WHERE extname = 'vector'")

                # Test table existence
                tables = await conn.fetch("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name IN ('documents', 'document_chunks', 'search_analytics')
                """)

                if len(tables) < 3:
                    return "degraded"

                return "healthy"

        except Exception as e:
            logger.error("Vector store health check failed", error=str(e))
            return "unhealthy"