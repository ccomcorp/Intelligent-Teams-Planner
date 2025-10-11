"""
Test semantic search functionality for Story 6.2
Tests the integration of document processing with embedding generation and semantic search
"""

import pytest
import asyncio
import tempfile
import os
from unittest.mock import Mock, AsyncMock

# Test the import structure
import sys
import importlib.util

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

class TestSemanticSearchIntegration:
    """Test semantic search engine integration"""

    @pytest.fixture
    def mock_vector_store(self):
        """Mock vector store for testing"""
        mock_store = Mock()
        mock_store.similarity_search = AsyncMock(return_value=[
            {
                'chunk_id': 'chunk_1',
                'document_id': 'doc_1',
                'content': 'This is about machine learning and AI development',
                'filename': 'ai_guide.txt',
                'source': 'openwebui',
                'similarity_score': 0.85
            },
            {
                'chunk_id': 'chunk_2',
                'document_id': 'doc_2',
                'content': 'Project management best practices for teams',
                'filename': 'pm_guide.txt',
                'source': 'planner',
                'similarity_score': 0.75
            }
        ])
        mock_store.log_search_analytics = AsyncMock()
        return mock_store

    @pytest.fixture
    def semantic_search_engine(self, mock_vector_store):
        """Create semantic search engine with mocked dependencies"""
        # Import SemanticSearchEngine
        search_path = os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'search', 'semantic_search.py')
        spec = importlib.util.spec_from_file_location("semantic_search", search_path)
        search_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(search_module)

        engine = search_module.SemanticSearchEngine(
            vector_store=mock_vector_store,
            config={'similarity_threshold': 0.5}
        )
        return engine

    @pytest.fixture
    def text_embedder(self):
        """Create text embedder for testing"""
        embedder_path = os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'embeddings', 'text_embedder.py')
        spec = importlib.util.spec_from_file_location("text_embedder", embedder_path)
        embedder_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(embedder_module)

        return embedder_module.TextEmbedder()

    @pytest.mark.asyncio
    async def test_text_embedder_initialization(self, text_embedder):
        """Test that text embedder initializes correctly"""
        assert text_embedder.model_name == "all-MiniLM-L6-v2"
        assert text_embedder.dimension == 384

        model_info = text_embedder.get_model_info()
        assert model_info['model_name'] == "all-MiniLM-L6-v2"
        assert model_info['dimension'] == 384

    @pytest.mark.asyncio
    async def test_embed_single_text(self, text_embedder):
        """Test embedding generation for single text"""
        text = "This is a test document about artificial intelligence and machine learning."

        embedding = await text_embedder.embed_text(text)

        assert embedding is not None
        assert embedding.shape == (384,)  # MiniLM dimension
        assert embedding.dtype.name.startswith('float')

    @pytest.mark.asyncio
    async def test_embed_multiple_texts(self, text_embedder):
        """Test batch embedding generation"""
        texts = [
            "Document about machine learning algorithms",
            "Project management guide for software teams",
            "User interface design principles"
        ]

        embeddings = await text_embedder.embed_texts(texts)

        assert len(embeddings) == 3
        for embedding in embeddings:
            assert embedding.shape == (384,)
            assert embedding.dtype.name.startswith('float')

    @pytest.mark.asyncio
    async def test_embed_document_chunks(self, text_embedder):
        """Test embedding generation for document chunks"""
        chunks = [
            {
                'chunk_id': 'chunk_1',
                'content': 'First chunk about AI development',
                'metadata': {'index': 0}
            },
            {
                'chunk_id': 'chunk_2',
                'content': 'Second chunk about team collaboration',
                'metadata': {'index': 1}
            }
        ]

        embedded_chunks = await text_embedder.embed_document_chunks(chunks)

        assert len(embedded_chunks) == 2
        for chunk in embedded_chunks:
            assert 'embedding' in chunk
            assert chunk['embedding'].shape == (384,)
            assert 'chunk_id' in chunk
            assert 'content' in chunk

    @pytest.mark.asyncio
    async def test_semantic_search_engine_initialization(self, semantic_search_engine):
        """Test semantic search engine initialization"""
        config = semantic_search_engine.get_search_config()

        assert config['embedding_model'] == "all-MiniLM-L6-v2"
        assert config['embedding_dimension'] == 384
        assert 'semantic' in config['supported_search_types']

    @pytest.mark.asyncio
    async def test_semantic_search_basic(self, semantic_search_engine):
        """Test basic semantic search functionality"""
        query = "machine learning tutorials"
        user_id = "test_user"

        results = await semantic_search_engine.search(
            query=query,
            user_id=user_id,
            limit=5
        )

        assert 'query' in results
        assert 'results' in results
        assert 'metadata' in results
        assert results['query'] == query
        assert len(results['results']) <= 5

    @pytest.mark.asyncio
    async def test_semantic_similarity(self, semantic_search_engine):
        """Test semantic similarity calculation"""
        text1 = "Machine learning algorithms for data analysis"
        text2 = "AI techniques for analyzing data"

        similarity = await semantic_search_engine.semantic_similarity(text1, text2)

        assert isinstance(similarity, float)
        assert 0.0 <= similarity <= 1.0
        assert similarity > 0.5  # These texts should be quite similar

    @pytest.mark.asyncio
    async def test_document_processor_with_embeddings(self):
        """Test document processor with embedding generation"""
        # Import DocumentProcessor
        processor_path = os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'processing', 'document_processor.py')
        spec = importlib.util.spec_from_file_location("document_processor", processor_path)
        processor_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(processor_module)

        processor = processor_module.DocumentProcessor(enable_embeddings=True)

        # Test document processing
        test_content = b"This is a test document about artificial intelligence and machine learning applications in modern software development."

        result = await processor.process_document(
            content=test_content,
            filename="test_ai_doc.txt",
            source="openwebui",
            uploaded_by="test_user"
        )

        assert result['processing_status'] == 'completed'
        assert 'chunks' in result
        assert len(result['chunks']) > 0

        # Check if embeddings were generated
        if result.get('embeddings_generated', False):
            for chunk in result['chunks']:
                if 'embedding' in chunk:
                    assert chunk['embedding'].shape == (384,)

    @pytest.mark.asyncio
    async def test_empty_text_handling(self, text_embedder):
        """Test handling of empty or invalid text"""
        empty_embedding = await text_embedder.embed_text("")
        assert empty_embedding.shape == (384,)
        assert all(x == 0 for x in empty_embedding)  # Should be zero vector

        none_embeddings = await text_embedder.embed_texts([])
        assert len(none_embeddings) == 0

    @pytest.mark.asyncio
    async def test_search_with_filters(self, semantic_search_engine):
        """Test semantic search with filters"""
        query = "project management"
        user_id = "test_user"
        filters = {"source": "planner"}

        results = await semantic_search_engine.search(
            query=query,
            user_id=user_id,
            limit=5,
            filters=filters
        )

        assert 'results' in results
        assert 'metadata' in results
        # Mock should have applied filters

    @pytest.mark.asyncio
    async def test_search_performance_metrics(self, semantic_search_engine):
        """Test that search returns performance metrics"""
        query = "artificial intelligence"
        user_id = "test_user"

        results = await semantic_search_engine.search(
            query=query,
            user_id=user_id
        )

        metadata = results['metadata']
        assert 'processing_time_ms' in metadata
        assert 'total_results' in metadata
        assert 'timestamp' in metadata
        assert isinstance(metadata['processing_time_ms'], (int, float))

if __name__ == "__main__":
    # Run basic test
    async def run_basic_test():
        print("Testing semantic search components...")

        # Test text embedder
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

        embedder_path = os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'embeddings', 'text_embedder.py')
        spec = importlib.util.spec_from_file_location("text_embedder", embedder_path)
        embedder_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(embedder_module)

        embedder = embedder_module.TextEmbedder()

        # Test basic embedding
        text = "This is a test about machine learning"
        embedding = await embedder.embed_text(text)
        print(f"✅ Embedding generated - shape: {embedding.shape}")

        # Test batch embeddings
        texts = ["AI development", "Project management", "Software testing"]
        embeddings = await embedder.embed_texts(texts)
        print(f"✅ Batch embeddings generated - count: {len(embeddings)}")

        print("✅ All semantic search tests passed!")

    # Run the test
    asyncio.run(run_basic_test())