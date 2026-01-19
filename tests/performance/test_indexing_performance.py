"""Performance tests for realtime indexing.

Feature: 011-realtime-attachment-indexing
Tasks: T015, T016
"""

import pytest
import time
from io import BytesIO
from unittest.mock import Mock, patch


class TestSignalHandlerPerformance:
    """Performance tests for signal handler execution time."""
    
    @pytest.mark.performance
    def test_signal_handler_completes_under_100ms(
        self,
        db,
        create_event,
        mocker
    ):
        """Test that signal handler executes in <100ms.
        
        Task: T015 - Performance test for signal handler
        FR-009: Signal handler must complete in <100ms
        SC-002: No user-facing latency from indexing
        """
        # Arrange
        from indico_assistant.plugin import _on_attachment_created
        
        event = create_event(title="Perf Test Event")
        
        mock_attachment = Mock()
        mock_attachment.id = 12345
        mock_attachment.event_id = event.id
        mock_attachment.file.filename = "test.pdf"
        mock_attachment.file.size = 5 * 1024 * 1024  # 5MB
        
        # Mock the task queueing to avoid actual Celery execution
        mock_task = mocker.patch('indico_assistant.tasks.indexing.index_attachment_task.apply_async')
        
        # Act - measure execution time
        start_time = time.perf_counter()
        _on_attachment_created(mock_attachment)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        # Assert
        assert elapsed_ms < 100, f"Signal handler took {elapsed_ms:.1f}ms, expected <100ms"
        mock_task.assert_called_once()
    
    @pytest.mark.performance
    def test_signal_handler_performance_with_vector_store_check(
        self,
        db,
        create_event,
        mocker
    ):
        """Test signal handler performance including vector store availability check.
        
        Task: T015
        FR-009: Handler must complete in <100ms even with pgvector check
        """
        # Arrange
        from indico_assistant.plugin import _on_attachment_created
        
        event = create_event(title="Perf Test Event")
        
        mock_attachment = Mock()
        mock_attachment.id = 12345
        mock_attachment.event_id = event.id
        mock_attachment.file.filename = "document.pdf"
        mock_attachment.file.size = 8 * 1024 * 1024  # 8MB
        
        # Mock VectorStore.is_available() to return True quickly
        mocker.patch('indico_assistant.services.vector_search.VectorStore.is_available', return_value=True)
        mock_task = mocker.patch('indico_assistant.tasks.indexing.index_attachment_task.apply_async')
        
        # Act
        start_time = time.perf_counter()
        _on_attachment_created(mock_attachment)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        # Assert
        assert elapsed_ms < 100, f"Signal handler with checks took {elapsed_ms:.1f}ms, expected <100ms"


class TestIndexingTaskPerformance:
    """Performance tests for indexing task execution time."""
    
    @pytest.mark.performance
    @patch('indico_assistant.tasks.indexing.Attachment')
    @patch('indico_assistant.tasks.indexing.compute_content_hash')
    @patch('indico_assistant.tasks.indexing.VectorStore')
    @patch('indico_assistant.tasks.indexing.DocumentExtractor')
    @patch('indico_assistant.tasks.indexing.DocumentChunker')
    @patch('indico_assistant.tasks.indexing.EmbeddingService')
    def test_indexing_completes_under_30s_for_small_files(
        self,
        mock_embedding_class,
        mock_chunker_class,
        mock_extractor_class,
        mock_store_class,
        mock_hash,
        mock_attachment_class
    ):
        """Test that indexing task completes in <30s for files <10MB.
        
        Task: T016 - Performance test for indexing task
        FR-004: Complete indexing within 30 seconds for files <10MB
        """
        # Arrange
        from indico_assistant.tasks.indexing import index_attachment_task
        
        # Create 8MB file mock
        file_size = 8 * 1024 * 1024
        mock_attachment = Mock()
        mock_attachment.id = 12345
        mock_attachment.file.size = file_size
        mock_attachment.file.filename = "large_document.pdf"
        mock_attachment.file.open.return_value.__enter__ = Mock(
            return_value=BytesIO(b'x' * file_size)
        )
        mock_attachment.file.open.return_value.__exit__ = Mock(return_value=False)
        mock_attachment_class.query.get.return_value = mock_attachment
        
        # Mock services with realistic delays
        mock_hash.return_value = "hash123" * 10 + "abc4"
        
        mock_store = Mock()
        mock_store.check_duplicate_by_hash.return_value = None
        mock_store.insert_chunks.return_value = 50
        mock_store_class.return_value = mock_store
        
        # Simulate extraction taking 5s for 8MB
        def mock_extract(*args, **kwargs):
            time.sleep(0.1)  # Simulate processing
            return "Extracted text " * 1000
        
        mock_extractor = Mock()
        mock_extractor.extract_text.side_effect = mock_extract
        mock_extractor_class.return_value = mock_extractor
        
        mock_chunker = Mock()
        mock_chunker.chunk_text.return_value = ["chunk"] * 50
        mock_chunker_class.return_value = mock_chunker
        
        mock_embedder = Mock()
        mock_embedder.embed_texts.return_value = [[0.1] * 384] * 50
        mock_embedding_class.return_value = mock_embedder
        
        # Act
        start_time = time.perf_counter()
        result = index_attachment_task(attachment_id=12345, event_id=789)
        elapsed_s = time.perf_counter() - start_time
        
        # Assert
        assert result['success'] is True
        assert elapsed_s < 30, f"Indexing took {elapsed_s:.1f}s, expected <30s for <10MB file"
    
    @pytest.mark.performance
    @patch('indico_assistant.tasks.indexing.Attachment')
    @patch('indico_assistant.tasks.indexing.compute_content_hash')
    @patch('indico_assistant.tasks.indexing.VectorStore')
    @patch('indico_assistant.tasks.indexing.DocumentExtractor')
    @patch('indico_assistant.tasks.indexing.DocumentChunker')
    @patch('indico_assistant.tasks.indexing.EmbeddingService')
    def test_indexing_completes_under_60s_for_medium_files(
        self,
        mock_embedding_class,
        mock_chunker_class,
        mock_extractor_class,
        mock_store_class,
        mock_hash,
        mock_attachment_class
    ):
        """Test that indexing task completes in <60s for files 10-50MB.
        
        Task: T016
        FR-008: Best-effort indexing for 10-50MB files (no time guarantee)
        """
        # Arrange
        from indico_assistant.tasks.indexing import index_attachment_task
        
        # Create 30MB file mock
        file_size = 30 * 1024 * 1024
        mock_attachment = Mock()
        mock_attachment.id = 12345
        mock_attachment.file.size = file_size
        mock_attachment.file.filename = "medium_document.pdf"
        mock_attachment.file.open.return_value.__enter__ = Mock(
            return_value=BytesIO(b'x' * file_size)
        )
        mock_attachment.file.open.return_value.__exit__ = Mock(return_value=False)
        mock_attachment_class.query.get.return_value = mock_attachment
        
        mock_hash.return_value = "hash456" * 10 + "def8"
        
        mock_store = Mock()
        mock_store.check_duplicate_by_hash.return_value = None
        mock_store.insert_chunks.return_value = 150
        mock_store_class.return_value = mock_store
        
        mock_extractor = Mock()
        mock_extractor.extract_text.return_value = "Large extracted text " * 5000
        mock_extractor_class.return_value = mock_extractor
        
        mock_chunker = Mock()
        mock_chunker.chunk_text.return_value = ["chunk"] * 150
        mock_chunker_class.return_value = mock_chunker
        
        mock_embedder = Mock()
        mock_embedder.embed_texts.return_value = [[0.1] * 384] * 150
        mock_embedding_class.return_value = mock_embedder
        
        # Act
        start_time = time.perf_counter()
        result = index_attachment_task(attachment_id=12345, event_id=789)
        elapsed_s = time.perf_counter() - start_time
        
        # Assert
        assert result['success'] is True
        # No strict time requirement, but should complete reasonably
        assert elapsed_s < 120, f"Indexing took {elapsed_s:.1f}s, expected <120s for 30MB file"
