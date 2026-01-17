"""Unit tests for RAGService.

Feature: 007-tdd-gap-analysis
GAP: GAP-003 (Critical - LLM Integration)
Tasks: T020-T025

Tests the RAG (Retrieval-Augmented Generation) service including:
- Chunk retrieval
- Retrieval with filters
- Empty results handling
- Reranking/context building
"""

import pytest
from unittest.mock import MagicMock, patch

from indico_assistant.services.vector_search.rag import (
    RAGService,
    RAGResult,
    DocumentContext,
)
from indico_assistant.services.vector_search.search import SearchResult, SearchResponse


class TestRAGService:
    """Tests for RAGService."""

    @pytest.fixture
    def mock_search_service(self):
        """Create mock SearchService."""
        service = MagicMock()
        service.is_available = True
        return service

    @pytest.fixture
    def rag_service(self, mock_search_service):
        """Create RAGService with mocked search service."""
        return RAGService(
            search_service=mock_search_service,
            context_max_chunks=3,
            context_max_chars=2000,
            min_similarity=0.7
        )

    @pytest.fixture
    def sample_search_results(self):
        """Create sample search results."""
        return [
            SearchResult(
                content="Machine learning is a subset of artificial intelligence.",
                similarity=0.95,
                event_id=123,
                attachment_id=456,
                chunk_index=0,
                metadata={"filename": "intro.pdf", "page_number": 1}
            ),
            SearchResult(
                content="Deep learning uses neural networks with many layers.",
                similarity=0.88,
                event_id=123,
                attachment_id=457,
                chunk_index=1,
                metadata={"filename": "advanced.pdf"}
            ),
            SearchResult(
                content="Natural language processing enables text understanding.",
                similarity=0.82,
                event_id=124,
                attachment_id=458,
                chunk_index=0,
                metadata={"filename": "nlp.pdf", "page_number": 5}
            ),
        ]

    # =========================================================================
    # T021: test_retrieve_relevant_chunks
    # =========================================================================

    def test_retrieve_relevant_chunks_success(
        self, rag_service, mock_search_service, sample_search_results
    ):
        """Test get_context retrieves relevant document chunks."""
        mock_search_service.search.return_value = SearchResponse(
            success=True,
            results=sample_search_results,
            total=3,
            query="machine learning",
            search_time_ms=50
        )
        
        result = rag_service.get_context(
            query="What does the document say about machine learning?",
            event_id=123
        )
        
        assert result.should_use_rag is True
        assert result.context is not None
        assert result.context.has_context is True
        assert len(result.context.chunks) == 3

    def test_retrieve_relevant_chunks_builds_context_text(
        self, rag_service, mock_search_service, sample_search_results
    ):
        """Test retrieved chunks are formatted into context text."""
        mock_search_service.search.return_value = SearchResponse(
            success=True,
            results=sample_search_results[:1],
            total=1,
            query="test",
            search_time_ms=50
        )
        
        result = rag_service.get_context(query="What does the document say?", event_id=123)
        
        assert result.context is not None
        assert "Machine learning" in result.context.text
        assert "intro.pdf" in result.context.text

    def test_retrieve_relevant_chunks_extracts_sources(
        self, rag_service, mock_search_service, sample_search_results
    ):
        """Test source metadata is extracted from search results."""
        mock_search_service.search.return_value = SearchResponse(
            success=True,
            results=sample_search_results,
            total=3,
            query="test",
            search_time_ms=50
        )
        
        result = rag_service.get_context(query="What does the document say?", event_id=123)
        
        assert result.context is not None
        assert len(result.context.sources) == 3
        assert result.context.sources[0]["filename"] == "intro.pdf"
        assert result.context.sources[0]["page"] == 1
        assert result.context.sources[0]["event_id"] == 123

    # =========================================================================
    # T022: test_retrieval_with_filters
    # =========================================================================

    def test_retrieval_with_event_id_filter(
        self, rag_service, mock_search_service, sample_search_results
    ):
        """Test get_context passes event_id filter to search service."""
        mock_search_service.search.return_value = SearchResponse(
            success=True,
            results=sample_search_results[:1],
            total=1,
            query="test",
            search_time_ms=50
        )
        
        rag_service.get_context(query="What does the document say?", event_id=123)
        
        mock_search_service.search.assert_called_once()
        call_kwargs = mock_search_service.search.call_args[1]
        assert call_kwargs["event_id"] == 123

    def test_retrieval_with_event_ids_filter(
        self, rag_service, mock_search_service, sample_search_results
    ):
        """Test get_context passes event_ids list filter to search service."""
        mock_search_service.search.return_value = SearchResponse(
            success=True,
            results=sample_search_results,
            total=3,
            query="test",
            search_time_ms=50
        )
        
        rag_service.get_context(query="What does the document say?", event_ids=[123, 124, 125])
        
        call_kwargs = mock_search_service.search.call_args[1]
        assert call_kwargs["event_ids"] == [123, 124, 125]

    def test_retrieval_with_user_id_filter(
        self, rag_service, mock_search_service, sample_search_results
    ):
        """Test get_context passes user_id for permission filtering."""
        mock_search_service.search.return_value = SearchResponse(
            success=True,
            results=sample_search_results,
            total=3,
            query="test",
            search_time_ms=50
        )
        
        rag_service.get_context(query="What does the document say?", user_id=999)
        
        call_kwargs = mock_search_service.search.call_args[1]
        assert call_kwargs["user_id"] == 999

    def test_retrieval_force_bypasses_classification(
        self, rag_service, mock_search_service, sample_search_results
    ):
        """Test force=True retrieves even for SQL-like queries."""
        mock_search_service.search.return_value = SearchResponse(
            success=True,
            results=sample_search_results[:1],
            total=1,
            query="test",
            search_time_ms=50
        )
        
        # "how many" is a SQL keyword, normally wouldn't trigger RAG
        result = rag_service.get_context(
            query="how many registrations are there?",
            force=True
        )
        
        # With force=True, should still perform search
        mock_search_service.search.assert_called_once()
        assert result.should_use_rag is True

    # =========================================================================
    # T023: test_empty_results
    # =========================================================================

    def test_empty_results_no_matches(
        self, rag_service, mock_search_service
    ):
        """Test get_context handles no matching results."""
        mock_search_service.search.return_value = SearchResponse(
            success=True,
            results=[],
            total=0,
            query="obscure query",
            search_time_ms=20
        )
        
        result = rag_service.get_context(
            query="what about the presentation on quantum computing?"
        )
        
        assert result.context is None
        assert result.query_type == "document"

    def test_empty_results_search_error(
        self, rag_service, mock_search_service
    ):
        """Test get_context handles search service errors."""
        mock_search_service.search.return_value = SearchResponse(
            success=False,
            results=[],
            total=0,
            query="test",
            search_time_ms=0,
            error="Database connection failed"
        )
        
        result = rag_service.get_context(query="test query about documents")
        
        assert result.context is None

    def test_empty_results_service_unavailable(self, mock_search_service):
        """Test get_context when search service is unavailable."""
        mock_search_service.is_available = False
        rag_service = RAGService(search_service=mock_search_service)
        
        result = rag_service.get_context(query="what does the document say?")
        
        assert result.should_use_rag is False
        assert result.context is None

    def test_empty_results_sql_query_no_search(
        self, rag_service, mock_search_service
    ):
        """Test SQL-type queries don't trigger search without force."""
        result = rag_service.get_context(
            query="how many people registered for the event?"
        )
        
        # SQL query should not trigger RAG search
        mock_search_service.search.assert_not_called()
        assert result.should_use_rag is False
        assert result.query_type == "sql"

    # =========================================================================
    # T024: test_reranking (context building)
    # =========================================================================

    def test_context_respects_max_chunks(
        self, rag_service, mock_search_service
    ):
        """Test context building respects max chunks limit via top_k parameter."""
        # Create many results
        many_results = [
            SearchResult(
                content=f"Content chunk {i}",
                similarity=0.9 - (i * 0.01),
                event_id=123,
                attachment_id=400 + i,
                chunk_index=i,
                metadata={"filename": f"doc_{i}.pdf"}
            )
            for i in range(10)
        ]
        
        # Mock returns only first 3 (simulating what search service does with top_k=3)
        mock_search_service.search.return_value = SearchResponse(
            success=True,
            results=many_results[:3],  # Search respects top_k
            total=10,
            query="test",
            search_time_ms=50
        )
        
        result = rag_service.get_context(query="what about the presentation?")
        
        # Only max_chunks (3) should be in context (enforced by search top_k)
        assert result.context is not None
        assert len(result.context.chunks) == 3
        
        # Verify top_k was passed to search
        call_kwargs = mock_search_service.search.call_args[1]
        assert call_kwargs["top_k"] == 3

    def test_context_respects_max_chars(self, mock_search_service):
        """Test context building respects max characters limit."""
        rag_service = RAGService(
            search_service=mock_search_service,
            context_max_chunks=10,
            context_max_chars=200,  # Very small limit
            min_similarity=0.7
        )
        
        long_results = [
            SearchResult(
                content="A" * 100,  # 100 chars each
                similarity=0.95,
                event_id=123,
                attachment_id=450,
                chunk_index=i,
                metadata={"filename": "doc.pdf"}
            )
            for i in range(5)
        ]
        
        mock_search_service.search.return_value = SearchResponse(
            success=True,
            results=long_results,
            total=5,
            query="test",
            search_time_ms=50
        )
        
        result = rag_service.get_context(query="what does the document say?")
        
        assert result.context is not None
        # Should have truncated due to char limit
        assert len(result.context.text) <= 300  # Some overhead for formatting

    def test_context_preserves_similarity_order(
        self, rag_service, mock_search_service
    ):
        """Test results maintain similarity ranking in context."""
        results = [
            SearchResult(
                content="Most relevant content",
                similarity=0.99,
                event_id=123,
                attachment_id=450,
                chunk_index=0,
                metadata={"filename": "best.pdf"}
            ),
            SearchResult(
                content="Second best content",
                similarity=0.85,
                event_id=123,
                attachment_id=451,
                chunk_index=0,
                metadata={"filename": "good.pdf"}
            ),
        ]
        
        mock_search_service.search.return_value = SearchResponse(
            success=True,
            results=results,
            total=2,
            query="test",
            search_time_ms=50
        )
        
        result = rag_service.get_context(query="tell me about the presentation")
        
        assert result.context is not None
        # First source should be highest similarity
        assert result.context.sources[0]["similarity"] == 0.99
        assert result.context.sources[1]["similarity"] == 0.85


class TestRAGServiceQueryClassification:
    """Tests for RAGService.classify_query()."""

    @pytest.fixture
    def rag_service(self):
        """Create RAGService with mock search service."""
        mock_search = MagicMock()
        mock_search.is_available = True
        return RAGService(search_service=mock_search)

    def test_classify_query_document(self, rag_service):
        """Test document-related queries classified as 'document'."""
        document_queries = [
            "What does the presentation say about AI?",
            "Can you summarize the attached document?",
            "What is mentioned in the slides?",
            "According to the paper, what are the main findings?",
        ]
        
        for query in document_queries:
            result = rag_service.classify_query(query)
            assert result == "document", f"Query '{query}' should be classified as 'document'"

    def test_classify_query_sql(self, rag_service):
        """Test SQL-related queries classified as 'sql'."""
        sql_queries = [
            "How many people registered for the event?",
            "List all events in category Physics",
            "Who are the participants in session A?",
            "What is the total number of contributions?",
        ]
        
        for query in sql_queries:
            result = rag_service.classify_query(query)
            assert result == "sql", f"Query '{query}' should be classified as 'sql'"

    def test_classify_query_hybrid(self, rag_service):
        """Test mixed queries classified as 'hybrid'."""
        hybrid_queries = [
            "How many presentations mention machine learning?",
            "List the documents that discuss AI participants",
        ]
        
        for query in hybrid_queries:
            result = rag_service.classify_query(query)
            assert result == "hybrid", f"Query '{query}' should be classified as 'hybrid'"


class TestDocumentContext:
    """Tests for DocumentContext dataclass."""

    def test_has_context_true(self):
        """Test has_context returns True when content exists."""
        ctx = DocumentContext(
            text="Some context text",
            sources=[{"filename": "doc.pdf"}],
            chunks=[MagicMock()]
        )
        
        assert ctx.has_context is True

    def test_has_context_false_empty_text(self):
        """Test has_context returns False with empty text."""
        ctx = DocumentContext(
            text="",
            sources=[],
            chunks=[]
        )
        
        assert ctx.has_context is False

    def test_has_context_false_no_chunks(self):
        """Test has_context returns False with no chunks."""
        ctx = DocumentContext(
            text="Some text",
            sources=[],
            chunks=[]
        )
        
        assert ctx.has_context is False


class TestRAGServicePromptBuilding:
    """Tests for RAGService.build_rag_prompt()."""

    @pytest.fixture
    def rag_service(self):
        """Create RAGService with mock search service."""
        return RAGService(search_service=MagicMock())

    def test_build_rag_prompt_includes_context(self, rag_service):
        """Test prompt includes document context."""
        ctx = DocumentContext(
            text="Relevant document content here",
            sources=[],
            chunks=[]
        )
        
        prompt = rag_service.build_rag_prompt(
            question="What is the main topic?",
            context=ctx
        )
        
        assert "Relevant document content here" in prompt
        assert "document_context" in prompt

    def test_build_rag_prompt_with_base_prompt(self, rag_service):
        """Test prompt combines with base prompt."""
        ctx = DocumentContext(text="Context", sources=[], chunks=[])
        
        prompt = rag_service.build_rag_prompt(
            question="question",
            context=ctx,
            base_prompt="You are a helpful assistant."
        )
        
        assert "You are a helpful assistant" in prompt
        assert "Context" in prompt


class TestRAGServiceCitations:
    """Tests for RAGService citation formatting."""

    @pytest.fixture
    def rag_service(self):
        """Create RAGService with mock search service."""
        return RAGService(search_service=MagicMock())

    def test_format_citations_with_pages(self, rag_service):
        """Test citation formatting includes page numbers."""
        sources = [
            {"filename": "intro.pdf", "page": 5},
            {"filename": "advanced.pdf", "page": 12},
        ]
        
        citations = rag_service.format_citations(sources)
        
        assert "intro.pdf (page 5)" in citations
        assert "advanced.pdf (page 12)" in citations

    def test_format_citations_without_pages(self, rag_service):
        """Test citation formatting without page numbers."""
        sources = [{"filename": "summary.pdf"}]
        
        citations = rag_service.format_citations(sources)
        
        assert "summary.pdf" in citations
        assert "page" not in citations

    def test_format_citations_empty(self, rag_service):
        """Test empty sources returns empty string."""
        citations = rag_service.format_citations([])
        
        assert citations == ""

    def test_format_citations_deduplicates(self, rag_service):
        """Test duplicate sources are deduplicated."""
        sources = [
            {"filename": "doc.pdf", "page": 1},
            {"filename": "doc.pdf", "page": 1},  # Duplicate
            {"filename": "doc.pdf", "page": 2},  # Same file, different page
        ]
        
        citations = rag_service.format_citations(sources)
        
        # Should have 2 unique citations
        assert citations.count("doc.pdf") == 2
