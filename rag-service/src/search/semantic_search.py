"""
Semantic Search Engine implementation for Story 6.2
Provides context-aware search with natural language query processing
"""

import asyncio
import time
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timezone

import numpy as np
import structlog
from sentence_transformers import SentenceTransformer

logger = structlog.get_logger(__name__)


class SemanticSearchEngine:
    """
    Advanced semantic search engine with context-aware capabilities

    Features:
    - Natural language query processing
    - Semantic similarity matching
    - Query expansion and intent understanding
    - Personalized search results
    - Real-time search analytics
    """

    def __init__(
        self,
        vector_store,
        embedding_model: str = "all-MiniLM-L6-v2",
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize semantic search engine"""
        self.vector_store = vector_store
        self.config = config or {}

        # Initialize embedding model
        self.embedding_model_name = embedding_model
        self.embedding_model = None  # Lazy load
        self.embedding_dimension = 384  # Default for MiniLM

        # Search configuration
        self.default_limit = self.config.get('default_limit', 20)
        self.max_limit = self.config.get('max_limit', 100)
        self.similarity_threshold = self.config.get('similarity_threshold', 0.5)
        self.reranking_enabled = self.config.get('reranking_enabled', True)

        # Query preprocessing patterns
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being'
        }

        logger.info("SemanticSearchEngine initialized",
                   model=self.embedding_model_name,
                   dimension=self.embedding_dimension)

    async def _get_embedding_model(self) -> SentenceTransformer:
        """Lazy load embedding model"""
        if self.embedding_model is None:
            logger.info("Loading embedding model", model=self.embedding_model_name)
            # Load in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            self.embedding_model = await loop.run_in_executor(
                None,
                lambda: SentenceTransformer(self.embedding_model_name)
            )
            logger.info("Embedding model loaded successfully")
        return self.embedding_model

    async def search(
        self,
        query: str,
        user_id: str,
        limit: int = None,
        filters: Optional[Dict[str, Any]] = None,
        include_context: bool = True,
        search_type: str = "semantic"
    ) -> Dict[str, Any]:
        """
        Perform semantic search with comprehensive result processing

        Args:
            query: Natural language search query
            user_id: User performing the search
            limit: Maximum results to return
            filters: Additional search filters
            include_context: Whether to include context analysis
            search_type: Type of search (semantic, hybrid, similarity)

        Returns:
            Search results with metadata and analytics
        """
        start_time = time.time()

        try:
            # Validate and prepare parameters
            limit = min(limit or self.default_limit, self.max_limit)
            filters = filters or {}

            logger.info("Starting semantic search",
                       query=query[:100],
                       user_id=user_id,
                       limit=limit,
                       search_type=search_type)

            # Process query
            processed_query = await self._preprocess_query(query)

            # Generate query embedding
            query_embedding = await self._generate_query_embedding(processed_query)

            # Perform vector similarity search
            raw_results = await self.vector_store.similarity_search(
                query_embedding=query_embedding,
                limit=limit * 2,  # Get more for reranking
                filters=filters,
                similarity_threshold=self.similarity_threshold
            )

            # Post-process and rank results
            if self.reranking_enabled:
                ranked_results = await self._rerank_results(query, raw_results)
            else:
                ranked_results = raw_results

            # Limit to requested size
            final_results = ranked_results[:limit]

            # Add context analysis if requested
            if include_context:
                final_results = await self._add_context_analysis(
                    query, final_results, user_id
                )

            # Generate search analytics
            processing_time_ms = (time.time() - start_time) * 1000

            # Log search analytics
            await self.vector_store.log_search_analytics(
                query=query,
                user_id=user_id,
                results_count=len(final_results),
                processing_time_ms=processing_time_ms,
                filters=filters
            )

            # Prepare response
            response = {
                'query': query,
                'processed_query': processed_query,
                'results': final_results,
                'metadata': {
                    'total_results': len(final_results),
                    'processing_time_ms': processing_time_ms,
                    'search_type': search_type,
                    'similarity_threshold': self.similarity_threshold,
                    'reranking_enabled': self.reranking_enabled,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            }

            logger.info("Semantic search completed",
                       results_count=len(final_results),
                       processing_time_ms=processing_time_ms)

            return response

        except Exception as e:
            processing_time_ms = (time.time() - start_time) * 1000
            logger.error("Semantic search failed",
                        error=str(e),
                        query=query[:100],
                        processing_time_ms=processing_time_ms,
                        exc_info=True)

            # Return error response
            return {
                'query': query,
                'results': [],
                'metadata': {
                    'total_results': 0,
                    'processing_time_ms': processing_time_ms,
                    'error': str(e),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            }

    async def _preprocess_query(self, query: str) -> str:
        """Preprocess search query for better semantic matching"""
        # Basic text cleaning
        processed = query.strip().lower()

        # Remove excessive whitespace
        processed = ' '.join(processed.split())

        # Query expansion could be added here
        # - Synonym expansion
        # - Abbreviation expansion
        # - Domain-specific term expansion

        logger.debug("Query preprocessed",
                    original=query[:50],
                    processed=processed[:50])

        return processed

    async def _generate_query_embedding(self, query: str) -> np.ndarray:
        """Generate embedding for search query"""
        try:
            model = await self._get_embedding_model()

            # Generate embedding in thread pool
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: model.encode(query, convert_to_numpy=True, normalize_embeddings=True)
            )

            logger.debug("Query embedding generated",
                        query_length=len(query),
                        embedding_shape=embedding.shape)

            return embedding

        except Exception as e:
            logger.error("Failed to generate query embedding", error=str(e))
            raise

    async def _rerank_results(
        self,
        query: str,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Rerank search results using advanced scoring"""
        if not results:
            return results

        try:
            reranked_results = []

            for result in results:
                # Calculate enhanced relevance score
                enhanced_score = await self._calculate_enhanced_relevance(
                    query, result
                )

                # Add search snippet
                snippet = await self._generate_search_snippet(query, result)

                # Create enhanced result
                enhanced_result = {
                    **result,
                    'relevance_score': enhanced_score,
                    'search_snippet': snippet,
                    'reranked': True
                }

                reranked_results.append(enhanced_result)

            # Sort by enhanced relevance score
            reranked_results.sort(
                key=lambda x: x['relevance_score'],
                reverse=True
            )

            logger.debug("Results reranked",
                        original_count=len(results),
                        reranked_count=len(reranked_results))

            return reranked_results

        except Exception as e:
            logger.warning("Reranking failed, using original order", error=str(e))
            return results

    async def _calculate_enhanced_relevance(
        self,
        query: str,
        result: Dict[str, Any]
    ) -> float:
        """Calculate enhanced relevance score combining multiple factors"""
        base_score = result.get('similarity_score', 0.0)

        # Factor 1: Content length factor (prefer substantial content)
        content = result.get('content', '')
        length_factor = min(len(content) / 1000, 1.0) * 0.1

        # Factor 2: Source factor (weight by source reliability)
        source_weights = {
            'planner': 1.2,
            'teams': 1.1,
            'openwebui': 1.0
        }
        source_factor = source_weights.get(result.get('source', ''), 1.0) * 0.1

        # Factor 3: Recency factor (prefer newer content)
        # This would require timestamp data from result
        recency_factor = 0.0

        # Factor 4: Query term overlap (keyword matching boost)
        query_terms = set(query.lower().split())
        content_terms = set(content.lower().split())
        overlap_ratio = len(query_terms & content_terms) / len(query_terms) if query_terms else 0
        keyword_factor = overlap_ratio * 0.2

        # Combine all factors
        enhanced_score = (
            base_score * 0.6 +  # Base semantic similarity (60%)
            length_factor +     # Content length boost (10%)
            source_factor +     # Source reliability boost (10%)
            recency_factor +    # Recency boost (0% - not implemented)
            keyword_factor      # Keyword overlap boost (20%)
        )

        return min(enhanced_score, 1.0)

    async def _generate_search_snippet(
        self,
        query: str,
        result: Dict[str, Any],
        max_length: int = 200
    ) -> str:
        """Generate highlighted search snippet"""
        content = result.get('content', '')

        if not content:
            return ""

        # Simple snippet generation - find best matching segment
        query_terms = query.lower().split()
        content_lower = content.lower()

        # Find first occurrence of any query term
        best_position = 0
        for term in query_terms:
            pos = content_lower.find(term)
            if pos != -1:
                best_position = max(0, pos - 50)  # Start 50 chars before
                break

        # Extract snippet
        snippet = content[best_position:best_position + max_length]

        # Add ellipsis if truncated
        if best_position > 0:
            snippet = "..." + snippet
        if len(content) > best_position + max_length:
            snippet = snippet + "..."

        return snippet.strip()

    async def _add_context_analysis(
        self,
        query: str,
        results: List[Dict[str, Any]],
        user_id: str
    ) -> List[Dict[str, Any]]:
        """Add context analysis to search results"""
        if not results:
            return results

        try:
            # Analyze result patterns
            sources = set(r.get('source', '') for r in results)
            doc_types = set(r.get('filename', '').split('.')[-1] for r in results)

            # Add context metadata to each result
            enhanced_results = []
            for result in results:
                context = {
                    'result_index': len(enhanced_results),
                    'total_sources_found': len(sources),
                    'document_types_found': list(doc_types),
                    'query_analyzed': True
                }

                enhanced_result = {
                    **result,
                    'context': context
                }
                enhanced_results.append(enhanced_result)

            return enhanced_results

        except Exception as e:
            logger.warning("Context analysis failed", error=str(e))
            return results

    async def semantic_similarity(
        self,
        text1: str,
        text2: str
    ) -> float:
        """Calculate semantic similarity between two texts"""
        try:
            model = await self._get_embedding_model()

            # Generate embeddings
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                lambda: model.encode([text1, text2], convert_to_numpy=True, normalize_embeddings=True)
            )

            # Calculate cosine similarity
            similarity = np.dot(embeddings[0], embeddings[1])

            return float(similarity)

        except Exception as e:
            logger.error("Failed to calculate semantic similarity", error=str(e))
            return 0.0

    async def find_similar_documents(
        self,
        document_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Find documents similar to a given document"""
        try:
            # Get the source document
            source_doc = await self.vector_store.get_document(document_id)
            if not source_doc:
                return []

            # Use document content as query for similarity search
            content = source_doc.get('chunks', [{}])[0].get('content', '')
            if not content:
                return []

            # Search for similar documents
            query_embedding = await self._generate_query_embedding(content[:500])

            similar_docs = await self.vector_store.similarity_search(
                query_embedding=query_embedding,
                limit=limit + 1,  # +1 to exclude source document
                filters={'document_id': f"NOT {document_id}"}  # Exclude source
            )

            return similar_docs[:limit]

        except Exception as e:
            logger.error("Failed to find similar documents",
                        error=str(e), document_id=document_id)
            return []

    def get_search_config(self) -> Dict[str, Any]:
        """Get current search configuration"""
        return {
            'embedding_model': self.embedding_model_name,
            'embedding_dimension': self.embedding_dimension,
            'default_limit': self.default_limit,
            'max_limit': self.max_limit,
            'similarity_threshold': self.similarity_threshold,
            'reranking_enabled': self.reranking_enabled,
            'supported_search_types': ['semantic', 'similarity', 'hybrid']
        }