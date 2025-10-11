"""
Search API endpoints for Story 6.2
RESTful APIs for semantic search integration
"""

from typing import Dict, List, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel, Field
import structlog

from ..search.semantic_search import SemanticSearchEngine
from ..storage.vector_store import VectorStore
from ..storage.postgres_client import PostgresClient
from ..embeddings.text_embedder import TextEmbedder

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


# Pydantic models for request/response
class SearchRequest(BaseModel):
    """Search request model"""
    query: str = Field(..., description="Search query", min_length=1, max_length=1000)
    limit: Optional[int] = Field(20, description="Maximum results to return", ge=1, le=100)
    filters: Optional[Dict[str, Any]] = Field(None, description="Additional search filters")
    search_type: Optional[str] = Field("semantic", description="Type of search")
    include_context: Optional[bool] = Field(True, description="Include context analysis")

class SimilarityRequest(BaseModel):
    """Document similarity request model"""
    document_id: str = Field(..., description="Source document ID")
    limit: Optional[int] = Field(10, description="Maximum similar documents to return", ge=1, le=50)

class TextSimilarityRequest(BaseModel):
    """Text similarity request model"""
    text1: str = Field(..., description="First text", min_length=1, max_length=5000)
    text2: str = Field(..., description="Second text", min_length=1, max_length=5000)

class SearchResponse(BaseModel):
    """Search response model"""
    query: str
    results: List[Dict[str, Any]]
    metadata: Dict[str, Any]

class SimilarityResponse(BaseModel):
    """Similarity response model"""
    similarity_score: float
    metadata: Dict[str, Any]


# Dependency injection for services
async def get_search_engine() -> SemanticSearchEngine:
    """Get semantic search engine instance"""
    # This would typically be injected through dependency injection
    # For now, we'll create a mock instance
    # In production, this would be configured in main.py
    postgres_client = PostgresClient()
    await postgres_client.initialize()

    vector_store = VectorStore(postgres_client)
    await vector_store.initialize()

    search_engine = SemanticSearchEngine(vector_store)
    return search_engine

async def get_text_embedder() -> TextEmbedder:
    """Get text embedder instance"""
    return TextEmbedder()


@router.post("/semantic", response_model=SearchResponse)
async def semantic_search(
    request: SearchRequest,
    user_id: str = Query(..., description="User ID performing the search"),
    search_engine: SemanticSearchEngine = Depends(get_search_engine)
) -> SearchResponse:
    """
    Perform semantic search across documents

    This endpoint provides context-aware search capabilities that understand
    natural language queries and return semantically relevant results.
    """
    try:
        logger.info("Semantic search request",
                   query=request.query[:100],
                   user_id=user_id,
                   limit=request.limit)

        # Perform search
        search_results = await search_engine.search(
            query=request.query,
            user_id=user_id,
            limit=request.limit,
            filters=request.filters,
            include_context=request.include_context,
            search_type=request.search_type
        )

        return SearchResponse(**search_results)

    except Exception as e:
        logger.error("Semantic search failed",
                    error=str(e),
                    query=request.query[:100],
                    user_id=user_id)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/similar/{document_id}")
async def find_similar_documents(
    document_id: str,
    limit: int = Query(10, description="Maximum similar documents to return", ge=1, le=50),
    search_engine: SemanticSearchEngine = Depends(get_search_engine)
) -> Dict[str, Any]:
    """
    Find documents similar to a given document

    Returns documents that are semantically similar to the specified document
    based on content analysis and vector similarity.
    """
    try:
        logger.info("Similar documents request",
                   document_id=document_id,
                   limit=limit)

        # Find similar documents
        similar_docs = await search_engine.find_similar_documents(
            document_id=document_id,
            limit=limit
        )

        return {
            'source_document_id': document_id,
            'similar_documents': similar_docs,
            'metadata': {
                'count': len(similar_docs),
                'timestamp': datetime.now().isoformat()
            }
        }

    except Exception as e:
        logger.error("Similar documents search failed",
                    error=str(e),
                    document_id=document_id)
        raise HTTPException(
            status_code=500,
            detail=f"Similar documents search failed: {str(e)}"
        )


@router.post("/similarity", response_model=SimilarityResponse)
async def calculate_text_similarity(
    request: TextSimilarityRequest,
    search_engine: SemanticSearchEngine = Depends(get_search_engine)
) -> SimilarityResponse:
    """
    Calculate semantic similarity between two texts

    Returns a similarity score between 0 and 1, where 1 indicates
    identical semantic meaning and 0 indicates no semantic relationship.
    """
    try:
        logger.info("Text similarity request",
                   text1_length=len(request.text1),
                   text2_length=len(request.text2))

        # Calculate similarity
        similarity_score = await search_engine.semantic_similarity(
            text1=request.text1,
            text2=request.text2
        )

        return SimilarityResponse(
            similarity_score=similarity_score,
            metadata={
                'text1_length': len(request.text1),
                'text2_length': len(request.text2),
                'timestamp': datetime.now().isoformat()
            }
        )

    except Exception as e:
        logger.error("Text similarity calculation failed",
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Similarity calculation failed: {str(e)}"
        )


@router.get("/config")
async def get_search_config(
    search_engine: SemanticSearchEngine = Depends(get_search_engine)
) -> Dict[str, Any]:
    """
    Get current search engine configuration

    Returns information about the search engine settings,
    supported features, and model configuration.
    """
    try:
        config = search_engine.get_search_config()
        return {
            'search_config': config,
            'timestamp': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error("Failed to get search config", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get configuration: {str(e)}"
        )


@router.get("/health")
async def search_health_check(
    search_engine: SemanticSearchEngine = Depends(get_search_engine)
) -> Dict[str, Any]:
    """
    Health check for search service

    Returns the health status of the search engine and its dependencies.
    """
    try:
        # Check vector store health
        vector_store_health = await search_engine.vector_store.health_check()

        # Test basic search functionality
        test_query = "test"
        test_embedding = await search_engine._generate_query_embedding(test_query)
        embedding_service_health = "healthy" if test_embedding is not None else "unhealthy"

        return {
            'status': 'healthy',
            'components': {
                'search_engine': 'healthy',
                'vector_store': vector_store_health,
                'embedding_service': embedding_service_health
            },
            'timestamp': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error("Search health check failed", error=str(e))
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


@router.get("/analytics")
async def get_search_analytics(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    limit: int = Query(100, description="Maximum analytics records to return", ge=1, le=1000),
    search_engine: SemanticSearchEngine = Depends(get_search_engine)
) -> Dict[str, Any]:
    """
    Get search analytics data

    Returns analytics about search queries, performance, and usage patterns.
    """
    try:
        # This would typically query the search_analytics table
        # For now, return a basic response

        analytics_data = {
            'summary': {
                'total_searches': 0,
                'unique_users': 0,
                'average_processing_time_ms': 0,
                'popular_queries': []
            },
            'recent_searches': [],
            'metadata': {
                'filtered_by_user': user_id,
                'limit': limit,
                'timestamp': datetime.now().isoformat()
            }
        }

        return analytics_data

    except Exception as e:
        logger.error("Failed to get search analytics", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get analytics: {str(e)}"
        )