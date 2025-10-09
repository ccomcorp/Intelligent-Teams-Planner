"""
Semantic search engine with multi-source support
Story 6.2 Task 2: Implement Semantic Search Engine
Aligned with IMPLEMENTATION-PLAN.md unified query interface
"""

import asyncio
import time
from typing import Dict, Any, List, Optional
import re

import structlog
import numpy as np

from ..storage.vector_store import VectorStore
from ..processing.embeddings import EmbeddingGenerator

logger = structlog.get_logger(__name__)


class SemanticSearchEngine:
    """
    Unified semantic search engine supporting multi-source queries
    Provides cross-source search with source attribution and filtering
    """

    def __init__(self, vector_store: VectorStore, embedding_generator: EmbeddingGenerator):
        self.vector_store = vector_store
        self.embedding_generator = embedding_generator

        # Search configuration
        self.default_similarity_threshold = 0.5
        self.max_results_per_query = 100
        self.snippet_length = 200

        logger.info("SemanticSearchEngine initialized")

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
        similarity_threshold: float = None
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search across all sources

        Args:
            query: Search query text
            limit: Maximum results to return
            filters: Optional filters (source, task_id, etc.)
            user_id: User identifier for analytics
            similarity_threshold: Minimum similarity score

        Returns:
            List of search results with source attribution
        """
        start_time = time.time()

        try:
            logger.info("Processing semantic search",
                       query=query[:100],
                       user_id=user_id,
                       filters=filters)

            # Set default threshold
            if similarity_threshold is None:
                similarity_threshold = self.default_similarity_threshold

            # Generate query embedding
            query_embedding = await self.embedding_generator.generate_embedding(query)

            # Add user_id to filters
            if filters is None:
                filters = {}
            if user_id:
                filters["user_id"] = user_id

            # Perform vector similarity search
            raw_results = await self.vector_store.similarity_search(
                query_embedding=query_embedding,
                limit=min(limit * 2, self.max_results_per_query),  # Get more for post-processing
                filters=filters,
                similarity_threshold=similarity_threshold
            )

            # Post-process and enhance results
            enhanced_results = await self._enhance_search_results(query, raw_results)

            # Rank and filter results
            final_results = await self._rank_and_filter_results(
                query, enhanced_results, limit
            )

            processing_time = (time.time() - start_time) * 1000

            # Log search analytics
            await self.vector_store.log_search_analytics(
                query=query,
                user_id=user_id,
                results_count=len(final_results),
                processing_time_ms=processing_time,
                filters=filters
            )

            logger.info("Semantic search completed",
                       query=query[:50],
                       results=len(final_results),
                       processing_time=f"{processing_time:.2f}ms")

            return final_results

        except Exception as e:
            logger.error("Semantic search failed", error=str(e), query=query[:100])
            raise

    async def search_by_source(
        self,
        query: str,
        source: str,
        limit: int = 10,
        user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """
        Search within a specific source

        Args:
            query: Search query text
            source: Source to search (openwebui, teams, planner)
            limit: Maximum results to return
            user_id: User identifier

        Returns:
            List of search results from specified source
        """
        filters = {"source": source}
        return await self.search(query, limit, filters, user_id)

    async def search_by_task(
        self,
        query: str,
        task_id: str,
        limit: int = 10,
        user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """
        Search within documents related to a specific task

        Args:
            query: Search query text
            task_id: Planner task ID
            limit: Maximum results to return
            user_id: User identifier

        Returns:
            List of search results from specified task
        """
        filters = {"task_id": task_id}
        return await self.search(query, limit, filters, user_id)

    async def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining vector similarity and keyword matching

        Args:
            query: Search query text
            limit: Maximum results to return
            vector_weight: Weight for vector similarity score
            keyword_weight: Weight for keyword matching score
            user_id: User identifier

        Returns:
            List of hybrid search results
        """
        try:
            # Perform semantic search
            semantic_results = await self.search(query, limit * 2, user_id=user_id)

            # Add keyword matching scores
            enhanced_results = []
            for result in semantic_results:
                keyword_score = self._calculate_keyword_score(query, result["content"])

                # Combine scores
                combined_score = (
                    vector_weight * result["similarity_score"] +
                    keyword_weight * keyword_score
                )

                result["keyword_score"] = keyword_score
                result["combined_score"] = combined_score
                enhanced_results.append(result)

            # Sort by combined score and limit results
            enhanced_results.sort(key=lambda x: x["combined_score"], reverse=True)

            logger.info("Hybrid search completed",
                       query=query[:50],
                       results=len(enhanced_results[:limit]))

            return enhanced_results[:limit]

        except Exception as e:
            logger.error("Hybrid search failed", error=str(e), query=query[:100])
            raise

    async def _enhance_search_results(
        self,
        query: str,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Enhance search results with snippets and metadata"""
        enhanced_results = []

        for result in results:
            try:
                # Generate snippet
                snippet = self._generate_snippet(query, result["content"])

                # Add enhanced fields
                enhanced_result = {
                    **result,
                    "snippet": snippet,
                    "word_count": len(result["content"].split()),
                    "relevance_indicators": self._extract_relevance_indicators(
                        query, result["content"]
                    )
                }

                enhanced_results.append(enhanced_result)

            except Exception as e:
                logger.warning("Failed to enhance result", error=str(e))
                # Keep original result if enhancement fails
                enhanced_results.append(result)

        return enhanced_results

    async def _rank_and_filter_results(
        self,
        query: str,
        results: List[Dict[str, Any]],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Apply additional ranking and filtering logic"""
        try:
            # Calculate additional ranking factors
            for result in results:
                # Source priority (planner > teams > openwebui for business context)
                source_priority = {
                    "planner": 1.0,
                    "teams": 0.9,
                    "openwebui": 0.8
                }.get(result.get("source", "openwebui"), 0.7)

                # Recency boost (more recent documents slightly preferred)
                recency_boost = 1.0  # Could be enhanced with timestamp analysis

                # Content quality score
                content_quality = self._calculate_content_quality(result["content"])

                # Final relevance score
                final_score = (
                    result["similarity_score"] * 0.6 +
                    source_priority * 0.2 +
                    content_quality * 0.1 +
                    recency_boost * 0.1
                )

                result["final_relevance_score"] = final_score

            # Sort by final relevance score
            results.sort(key=lambda x: x["final_relevance_score"], reverse=True)

            # Apply limit
            return results[:limit]

        except Exception as e:
            logger.error("Failed to rank results", error=str(e))
            # Return original results if ranking fails
            return results[:limit]

    def _generate_snippet(self, query: str, content: str) -> str:
        """Generate a relevant snippet from content"""
        try:
            # Simple snippet generation - find query terms in content
            query_terms = set(query.lower().split())
            sentences = re.split(r'[.!?]+', content)

            # Score sentences by query term overlap
            scored_sentences = []
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                sentence_words = set(sentence.lower().split())
                overlap = len(query_terms.intersection(sentence_words))
                scored_sentences.append((overlap, sentence))

            # Get best sentence or first part of content
            if scored_sentences:
                scored_sentences.sort(key=lambda x: x[0], reverse=True)
                best_sentence = scored_sentences[0][1]

                # Ensure snippet isn't too long
                if len(best_sentence) > self.snippet_length:
                    best_sentence = best_sentence[:self.snippet_length] + "..."

                return best_sentence
            else:
                # Fallback to first part of content
                return content[:self.snippet_length] + ("..." if len(content) > self.snippet_length else "")

        except Exception as e:
            logger.warning("Failed to generate snippet", error=str(e))
            return content[:self.snippet_length] + ("..." if len(content) > self.snippet_length else "")

    def _calculate_keyword_score(self, query: str, content: str) -> float:
        """Calculate keyword matching score"""
        try:
            query_terms = set(query.lower().split())
            content_words = content.lower().split()
            content_set = set(content_words)

            if not query_terms or not content_words:
                return 0.0

            # Exact matches
            exact_matches = len(query_terms.intersection(content_set))

            # Partial matches (terms that contain query terms)
            partial_matches = 0
            for query_term in query_terms:
                for content_word in content_set:
                    if query_term in content_word and query_term != content_word:
                        partial_matches += 0.5
                        break

            # Calculate score
            total_score = exact_matches + partial_matches
            max_score = len(query_terms)

            return min(total_score / max_score, 1.0) if max_score > 0 else 0.0

        except Exception as e:
            logger.warning("Failed to calculate keyword score", error=str(e))
            return 0.0

    def _extract_relevance_indicators(self, query: str, content: str) -> List[str]:
        """Extract indicators of relevance (highlighted terms, etc.)"""
        try:
            indicators = []
            query_terms = [term.lower() for term in query.split()]

            for term in query_terms:
                # Find exact matches
                if term in content.lower():
                    indicators.append(f"exact_match:{term}")

                # Find partial matches
                words = content.lower().split()
                for word in words:
                    if term in word and term != word:
                        indicators.append(f"partial_match:{word}")
                        break

            return indicators[:5]  # Limit number of indicators

        except Exception as e:
            logger.warning("Failed to extract relevance indicators", error=str(e))
            return []

    def _calculate_content_quality(self, content: str) -> float:
        """Calculate content quality score"""
        try:
            if not content:
                return 0.0

            # Basic quality indicators
            word_count = len(content.split())
            char_count = len(content)

            # Prefer content with reasonable length
            if word_count < 10:
                length_score = 0.3
            elif word_count < 50:
                length_score = 0.7
            elif word_count < 500:
                length_score = 1.0
            else:
                length_score = 0.8  # Very long content might be less focused

            # Check for structured content (bullets, numbers, etc.)
            structure_score = 0.5
            if any(char in content for char in ['"', '-', '*']):
                structure_score += 0.2
            if any(content.count(str(i)) > 0 for i in range(1, 10)):
                structure_score += 0.2

            # Combine scores
            return min((length_score + structure_score) / 2, 1.0)

        except Exception as e:
            logger.warning("Failed to calculate content quality", error=str(e))
            return 0.5

    async def get_search_statistics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get search statistics"""
        try:
            # This would typically query the search_analytics table
            # For now, return basic stats
            return {
                "total_searches": 0,  # Would be queried from database
                "avg_results_per_search": 0.0,
                "most_common_sources": [],
                "avg_processing_time": 0.0
            }
        except Exception as e:
            logger.error("Failed to get search statistics", error=str(e))
            return {}

    async def health_check(self) -> str:
        """Check search engine health"""
        try:
            # Test embedding generation
            embedding_health = await self.embedding_generator.health_check()
            if embedding_health != "healthy":
                return "degraded"

            # Test vector store
            vector_health = await self.vector_store.health_check()
            if vector_health != "healthy":
                return "degraded"

            # Test basic search functionality
            test_results = await self.search("test query", limit=1)

            return "healthy"

        except Exception as e:
            logger.error("Search engine health check failed", error=str(e))
            return "unhealthy"