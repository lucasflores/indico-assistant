"""Unit tests for SearchService.

Feature: 007-tdd-gap-analysis
GAP: GAP-004 (Critical - LLM Integration)
Tasks: T026-T031

Tests the semantic search service including:
- Semantic search functionality
- Hybrid search
- Pagination
- Timeout handling
"""

import pytest
from unittest.mock import MagicMock, patch
import time

from indico_assistant.services.vector_search.search import (
    SearchService,
    SearchResult,
    SearchResponse,
    create_search_service,
)


class TestSearchService:
    """Tests for SearchService."""

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock EmbeddingService."""
        service = MagicMock()
        service.is_enabled = True
        service.embed_text.return_value = [0.1] * 384
        return service

    @pytest.fixture
    def mock_vector_store(self):
        """Create mock VectorStore."""
        store = MagicMock()
        store.is_available = True
        store.similarity_search.return_value = []
        return store

    @pytest.fixture
    def search_service(self, mock_embedding_service, mock_vector_store):
        """Create SearchService with mocked dependencies."""
        return SearchService(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
            default_top_k=5,
            default_threshold=0.7
        )

    @pytest.fixture
    def sample_raw_results(self):
        """Sample raw results from vector store."""
        return [
            {
                "content_text": "Machine learning fundamentals",
                "similarity": 0.95,
                "event_id": 123,
                "attachment_id": 456,
                "chunk_index": 0,
                "metadata_json": {"filename": "intro.pdf"}
            },
            {
                "content_text": "Deep learning applications",
                "similarity": 0.88,
                "event_id": 123,
                "attachment_id": 457,
                "chunk_index": 1,
                "metadata_json": {"filename": "advanced.pdf"}
            },
        ]

    # =========================================================================
    # T027: test_semantic_search
    # =========================================================================

    def test_semantic_search_success(
        self, search_service, mock_embedding_service, mock_vector_store, sample_raw_results
    ):
        """Test semantic search returns results successfully."""
        mock_vector_store.similarity_search.return_value = sample_raw_results
        
        response = search_service.search(query="machine learning")
        
        assert response.success is True
        assert len(response.results) == 2
        assert response.total == 2
        assert response.query == "machine learning"
        assert response.search_time_ms > 0

    def test_semantic_search_generates_embedding(
        self, search_service, mock_embedding_service, mock_vector_store
    ):
        """Test search generates query embedding."""
        mock_vector_store.similarity_search.return_value = []
        
        search_service.search(query="test query")
        
        mock_embedding_service.embed_text.assert_called_once_with("test query")

    def test_semantic_search_passes_embedding_to_store(
        self, search_service, mock_embedding_service, mock_vector_store
    ):
        """Test search passes generated embedding to vector store."""
        mock_embedding_service.embed_text.return_value = [0.5] * 384
        mock_vector_store.similarity_search.return_value = []
        
        search_service.search(query="test")
        
        call_kwargs = mock_vector_store.similarity_search.call_args[1]
        assert call_kwargs["query_embedding"] == [0.5] * 384

    def test_semantic_search_converts_raw_results(
        self, search_service, mock_vector_store, sample_raw_results
    ):
        """Test raw results are converted to SearchResult objects."""
        mock_vector_store.similarity_search.return_value = sample_raw_results
        
        response = search_service.search(query="test")
        
        assert all(isinstance(r, SearchResult) for r in response.results)
        assert response.results[0].content == "Machine learning fundamentals"
        assert response.results[0].similarity == 0.95
        assert response.results[0].metadata["filename"] == "intro.pdf"

    def test_semantic_search_empty_query_fails(self, search_service):
        """Test search with empty query returns error response."""
        response = search_service.search(query="")
        
        assert response.success is False
        assert response.error == "Query cannot be empty"

    def test_semantic_search_whitespace_query_fails(self, search_service):
        """Test search with whitespace-only query returns error."""
        response = search_service.search(query="   \n\t  ")
        
        assert response.success is False
        assert response.error == "Query cannot be empty"

    # =========================================================================
    # T028: test_hybrid_search
    # =========================================================================

    def test_hybrid_search_with_event_id(
        self, search_service, mock_vector_store, sample_raw_results
    ):
        """Test search with event_id filter."""
        mock_vector_store.similarity_search.return_value = sample_raw_results
        
        search_service.search(query="test", event_id=123)
        
        call_kwargs = mock_vector_store.similarity_search.call_args[1]
        assert call_kwargs["event_id"] == 123

    def test_hybrid_search_with_event_ids(
        self, search_service, mock_vector_store, sample_raw_results
    ):
        """Test search with multiple event_ids filter."""
        mock_vector_store.similarity_search.return_value = sample_raw_results
        
        search_service.search(query="test", event_ids=[123, 124, 125])
        
        call_kwargs = mock_vector_store.similarity_search.call_args[1]
        assert call_kwargs["event_ids"] == [123, 124, 125]

    def test_hybrid_search_with_custom_threshold(
        self, search_service, mock_vector_store
    ):
        """Test search with custom similarity threshold."""
        mock_vector_store.similarity_search.return_value = []
        
        search_service.search(query="test", threshold=0.9)
        
        call_kwargs = mock_vector_store.similarity_search.call_args[1]
        assert call_kwargs["threshold"] == 0.9

    def test_hybrid_search_uses_default_threshold(
        self, search_service, mock_vector_store
    ):
        """Test search uses default threshold when not specified."""
        mock_vector_store.similarity_search.return_value = []
        
        search_service.search(query="test")
        
        call_kwargs = mock_vector_store.similarity_search.call_args[1]
        assert call_kwargs["threshold"] == 0.7  # default

    # =========================================================================
    # T029: test_search_pagination
    # =========================================================================

    def test_search_pagination_top_k(
        self, search_service, mock_vector_store, sample_raw_results
    ):
        """Test search with custom top_k limit."""
        mock_vector_store.similarity_search.return_value = sample_raw_results[:1]
        
        search_service.search(query="test", top_k=1)
        
        call_kwargs = mock_vector_store.similarity_search.call_args[1]
        assert call_kwargs["top_k"] == 1

    def test_search_pagination_uses_default_top_k(
        self, search_service, mock_vector_store
    ):
        """Test search uses default top_k when not specified."""
        mock_vector_store.similarity_search.return_value = []
        
        search_service.search(query="test")
        
        call_kwargs = mock_vector_store.similarity_search.call_args[1]
        assert call_kwargs["top_k"] == 5  # default

    def test_search_pagination_large_top_k(
        self, search_service, mock_vector_store
    ):
        """Test search handles large top_k value."""
        mock_vector_store.similarity_search.return_value = []
        
        search_service.search(query="test", top_k=1000)
        
        call_kwargs = mock_vector_store.similarity_search.call_args[1]
        assert call_kwargs["top_k"] == 1000

    # =========================================================================
    # T030: test_search_timeout
    # =========================================================================

    def test_search_handles_embedding_error(
        self, search_service, mock_embedding_service
    ):
        """Test search handles embedding generation failure."""
        mock_embedding_service.embed_text.side_effect = RuntimeError("Model unavailable")
        
        response = search_service.search(query="test")
        
        assert response.success is False
        assert "Model unavailable" in response.error

    def test_search_handles_store_error(
        self, search_service, mock_vector_store
    ):
        """Test search handles vector store failure."""
        mock_vector_store.similarity_search.side_effect = Exception("Database timeout")
        
        response = search_service.search(query="test")
        
        assert response.success is False
        assert "Database timeout" in response.error

    def test_search_unavailable_embedding_service(
        self, mock_embedding_service, mock_vector_store
    ):
        """Test search returns error when embedding service disabled."""
        mock_embedding_service.is_enabled = False
        service = SearchService(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store
        )
        
        response = service.search(query="test")
        
        assert response.success is False
        assert "not available" in response.error

    def test_search_unavailable_vector_store(
        self, mock_embedding_service, mock_vector_store
    ):
        """Test search returns error when vector store unavailable."""
        mock_vector_store.is_available = False
        service = SearchService(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store
        )
        
        response = service.search(query="test")
        
        assert response.success is False
        assert "not available" in response.error

    def test_search_records_timing(
        self, search_service, mock_vector_store
    ):
        """Test search records execution time."""
        mock_vector_store.similarity_search.return_value = []
        
        response = search_service.search(query="test")
        
        assert response.search_time_ms >= 0
        assert isinstance(response.search_time_ms, float)


class TestSearchServiceAvailability:
    """Tests for SearchService.is_available property."""

    def test_is_available_both_services_up(self):
        """Test is_available True when both services available."""
        mock_embedding = MagicMock()
        mock_embedding.is_enabled = True
        mock_store = MagicMock()
        mock_store.is_available = True
        
        service = SearchService(
            embedding_service=mock_embedding,
            vector_store=mock_store
        )
        
        assert service.is_available is True

    def test_is_available_embedding_disabled(self):
        """Test is_available False when embedding service disabled."""
        mock_embedding = MagicMock()
        mock_embedding.is_enabled = False
        mock_store = MagicMock()
        mock_store.is_available = True
        
        service = SearchService(
            embedding_service=mock_embedding,
            vector_store=mock_store
        )
        
        assert service.is_available is False

    def test_is_available_store_unavailable(self):
        """Test is_available False when vector store unavailable."""
        mock_embedding = MagicMock()
        mock_embedding.is_enabled = True
        mock_store = MagicMock()
        mock_store.is_available = False
        
        service = SearchService(
            embedding_service=mock_embedding,
            vector_store=mock_store
        )
        
        assert service.is_available is False


class TestSearchServiceStats:
    """Tests for SearchService.get_stats()."""

    def test_get_stats_returns_combined_info(self):
        """Test get_stats combines embedding and store stats."""
        mock_embedding = MagicMock()
        mock_embedding.is_enabled = True
        mock_embedding.health_check.return_value = {
            "status": "healthy",
            "model": "test-model"
        }
        
        mock_store = MagicMock()
        mock_store.is_available = True
        mock_store.get_stats.return_value = {
            "total_vectors": 1000,
            "dimensions": 384
        }
        
        service = SearchService(
            embedding_service=mock_embedding,
            vector_store=mock_store
        )
        
        stats = service.get_stats()
        
        assert stats["available"] is True
        assert stats["embedding_service"]["status"] == "healthy"
        assert stats["vector_store"]["total_vectors"] == 1000

    def test_get_stats_with_event_filter(self):
        """Test get_stats passes event_id to store."""
        mock_embedding = MagicMock()
        mock_embedding.is_enabled = True
        mock_embedding.health_check.return_value = {}
        
        mock_store = MagicMock()
        mock_store.is_available = True
        mock_store.get_stats.return_value = {}
        
        service = SearchService(
            embedding_service=mock_embedding,
            vector_store=mock_store
        )
        
        service.get_stats(event_id=123)
        
        mock_store.get_stats.assert_called_with(123)


class TestSearchResponse:
    """Tests for SearchResponse dataclass."""

    def test_search_response_success(self):
        """Test creating successful SearchResponse."""
        response = SearchResponse(
            success=True,
            results=[],
            total=0,
            query="test",
            search_time_ms=50.0
        )
        
        assert response.success is True
        assert response.error is None

    def test_search_response_error(self):
        """Test creating error SearchResponse."""
        response = SearchResponse(
            success=False,
            results=[],
            total=0,
            query="test",
            search_time_ms=10.0,
            error="Something went wrong"
        )
        
        assert response.success is False
        assert response.error == "Something went wrong"


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_search_result_creation(self):
        """Test creating SearchResult."""
        result = SearchResult(
            content="Test content",
            similarity=0.95,
            event_id=123,
            attachment_id=456,
            chunk_index=0,
            metadata={"filename": "test.pdf"}
        )
        
        assert result.content == "Test content"
        assert result.similarity == 0.95
        assert result.event_id == 123
        assert result.metadata["filename"] == "test.pdf"


class TestCreateSearchServiceFactory:
    """Tests for create_search_service factory function."""

    def test_factory_creates_service(self):
        """Test factory creates SearchService instance."""
        mock_plugin = MagicMock()
        mock_plugin.settings.get.side_effect = lambda key, default=None: {
            "max_search_results": 10,
            "similarity_threshold": 0.8,
            "embedding_model": "test-model",
            "embedding_dimensions": 384,
            "embedding_batch_size": 32,
            "vector_search_enabled": True,
        }.get(key, default)
        
        with patch(
            "indico_assistant.services.vector_search.search.VectorStore"
        ) as MockStore:
            MockStore.return_value = MagicMock(is_available=True)
            
            service = create_search_service(mock_plugin)
            
            assert isinstance(service, SearchService)
