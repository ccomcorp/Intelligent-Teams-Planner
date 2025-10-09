"""
RAG Service - Document Processing and Semantic Search
Epic 6: Data Management and Analytics
Stories: 6.1 (Document Processing), 6.2 (Vector Database Semantic Search)
"""

import os
import asyncio
import json
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import structlog

from .storage.vector_store import VectorStore
from .storage.postgres_client import PostgresClient
from .processing.document_processor import DocumentProcessor
from .processing.embeddings import EmbeddingGenerator
from .query.semantic_search import SemanticSearchEngine

# Configure structured logging
structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(10),  # DEBUG level
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True
)

logger = structlog.get_logger(__name__)

# Global service instances
vector_store: VectorStore = None
postgres_client: PostgresClient = None
document_processor: DocumentProcessor = None
embedding_generator: EmbeddingGenerator = None
search_engine: SemanticSearchEngine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global vector_store, postgres_client, document_processor, embedding_generator, search_engine

    try:
        # Initialize database connections
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL must be set")

        postgres_client = PostgresClient(database_url)
        await postgres_client.initialize()

        # Initialize vector store with 768 dimensions
        vector_store = VectorStore(postgres_client, dimension=768)
        await vector_store.initialize()

        # Initialize processing components
        embedding_generator = EmbeddingGenerator()
        await embedding_generator.initialize()
        document_processor = DocumentProcessor()

        # Initialize search engine
        search_engine = SemanticSearchEngine(vector_store, embedding_generator)

        logger.info("RAG Service initialized successfully")
        yield

    except Exception as e:
        logger.error("Failed to initialize RAG Service", error=str(e))
        raise
    finally:
        # Cleanup
        if postgres_client:
            await postgres_client.close()


# Create FastAPI app
app = FastAPI(
    title="Intelligent Teams Planner RAG Service",
    description="Document processing and semantic search service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class DocumentUploadResponse(BaseModel):
    """Response for document upload (aligned with implementation plan)"""
    document_id: str
    filename: str
    source: str
    file_size: int
    processing_status: str
    chunks_created: int


class SearchRequest(BaseModel):
    """Search request model (aligned with implementation plan)"""
    query: str = Field(..., description="Search query")
    top_k: int = Field(default=10, ge=1, le=100, alias="limit")
    filters: Dict[str, Any] = Field(default_factory=dict)
    user_id: str = Field(default="default")


class SearchResult(BaseModel):
    """Individual search result (aligned with implementation plan)"""
    document_id: str
    chunk_id: str
    content: str
    filename: str
    source: str
    task_id: Optional[str] = None
    task_title: Optional[str] = None
    chunk_index: int
    score: float = Field(alias="similarity_score")
    snippet: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Search response model"""
    query: str
    results: List[SearchResult]
    total_results: int
    processing_time_ms: float


# Dependency injection
async def get_vector_store() -> VectorStore:
    """Get vector store instance"""
    return vector_store


async def get_search_engine() -> SemanticSearchEngine:
    """Get search engine instance"""
    return search_engine


async def get_document_processor() -> DocumentProcessor:
    """Get document processor instance"""
    return document_processor


def _parse_metadata(metadata_value: Any) -> Dict[str, Any]:
    """Safely parse metadata from database"""
    if metadata_value is None:
        return {}
    if isinstance(metadata_value, dict):
        return metadata_value
    if isinstance(metadata_value, str):
        try:
            return json.loads(metadata_value)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse metadata JSON", metadata=metadata_value)
            return {}
    return {}


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database connectivity
        db_status = await postgres_client.health_check()

        # Check vector store
        vector_status = await vector_store.health_check()

        overall_status = "healthy" if all([
            db_status == "healthy",
            vector_status == "healthy"
        ]) else "degraded"

        return {
            "status": overall_status,
            "timestamp": asyncio.get_event_loop().time(),
            "services": {
                "database": db_status,
                "vector_store": vector_status
            },
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# Document upload endpoint
@app.post("/api/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    source: str = Form("openwebui"),
    source_id: Optional[str] = Form(None),
    user_id: str = Form("default"),
    task_id: Optional[str] = Form(None),
    task_title: Optional[str] = Form(None),
    conversation_id: Optional[str] = Form(None),
    processor: DocumentProcessor = Depends(get_document_processor),
    vector_store: VectorStore = Depends(get_vector_store)
):
    """Upload and process document"""
    try:
        logger.info("Processing document upload", filename=file.filename, user_id=user_id)

        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        # Read file content
        content = await file.read()

        # Process document with multi-source support
        processed_doc = await processor.process_document(
            content=content,
            filename=file.filename,
            source=source,
            source_id=source_id,
            uploaded_by=user_id,
            task_id=task_id,
            task_title=task_title,
            conversation_id=conversation_id
        )

        # Generate embeddings for chunks
        for chunk in processed_doc["chunks"]:
            chunk["embedding"] = await embedding_generator.generate_embedding(
                chunk["content"]
            )

        # Store in vector database
        chunks_created = await vector_store.store_document(processed_doc)

        return DocumentUploadResponse(
            document_id=processed_doc["document_id"],
            filename=file.filename,
            source=source,
            file_size=len(content),
            processing_status="completed",
            chunks_created=chunks_created
        )

    except Exception as e:
        logger.error("Error processing document upload", error=str(e), filename=file.filename)
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")


# Search endpoint
@app.post("/api/query", response_model=SearchResponse)
async def query_documents(
    request: SearchRequest,
    search_engine: SemanticSearchEngine = Depends(get_search_engine)
):
    """Perform semantic search"""
    try:
        start_time = asyncio.get_event_loop().time()

        logger.info("Processing search request", query=request.query, user_id=request.user_id)

        # Perform search
        results = await search_engine.search(
            query=request.query,
            limit=request.top_k,
            filters=request.filters,
            user_id=request.user_id
        )

        processing_time = (asyncio.get_event_loop().time() - start_time) * 1000

        # Convert to response format
        search_results = [
            SearchResult(
                document_id=result["document_id"],
                chunk_id=result["chunk_id"],
                content=result["content"],
                filename=result["filename"],
                source=result["source"],
                task_id=result.get("task_id"),
                task_title=result.get("task_title"),
                chunk_index=result["chunk_index"],
                similarity_score=result["similarity_score"],
                snippet=result["snippet"],
                metadata=_parse_metadata(result.get("chunk_metadata"))
            )
            for result in results
        ]

        return SearchResponse(
            query=request.query,
            results=search_results,
            total_results=len(search_results),
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error("Error processing search request", error=str(e), query=request.query)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# Document retrieval
@app.get("/api/documents/{document_id}")
async def get_document(
    document_id: str,
    vector_store: VectorStore = Depends(get_vector_store)
):
    """Get document by ID"""
    try:
        document = await vector_store.get_document(document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving document", error=str(e), document_id=document_id)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve document: {str(e)}")


# List documents
@app.get("/api/documents")
async def list_documents(
    user_id: str = "default",
    limit: int = 50,
    offset: int = 0,
    vector_store: VectorStore = Depends(get_vector_store)
):
    """List user's documents"""
    try:
        documents = await vector_store.list_documents(
            user_id=user_id,
            limit=limit,
            offset=offset
        )

        return {
            "documents": documents,
            "total": len(documents),
            "offset": offset,
            "limit": limit
        }

    except Exception as e:
        logger.error("Error listing documents", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


def main():
    """Main entry point"""
    try:
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "7120"))

        logger.info("Starting RAG Service", host=host, port=port)

        import uvicorn
        uvicorn.run(
            "src.main:app",
            host=host,
            port=port,
            reload=os.getenv("ENVIRONMENT") == "development",
            log_level="info"
        )

    except Exception as e:
        logger.error("Failed to start RAG service", error=str(e))
        raise


if __name__ == "__main__":
    main()