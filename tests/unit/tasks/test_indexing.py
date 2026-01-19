"""Unit tests for indexing task workflow.

Feature: 011-realtime-attachment-indexing
Tasks: T013
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from io import BytesIO
from indico_assistant.schemas.document import IndexingTaskResult


class TestIndexingTaskWorkflow:
    """Tests for index_attachment_task workflow."""
    
    @patch('indico_assistant.tasks.indexing.Attachment')
    @patch('indico_assistant.tasks.indexing.compute_content_hash')
    @patch('indico_assistant.tasks.indexing.VectorStore')
    def test_task_returns_skipped_for_duplicate(
        self,
        mock_store_class,
        mock_hash,
        mock_attachment_class
    ):
        """Test that task returns 'skipped' status for duplicate documents.
        
        Task: T013 - Unit test for task workflow
        FR-006: Skip re-indexing when hash matches
        """
        # Arrange
        from indico_assistant.tasks.indexing import index_attachment_task
        
        mock_attachment = Mock()
        mock_attachment.id = 12345
        mock_attachment.file.size = 5 * 1024 * 1024
        mock_attachment.file.open.return_value.__enter__ = Mock(return_value=BytesIO(b'test'))
        mock_attachment.file.open.return_value.__exit__ = Mock(return_value=False)
        mock_attachment_class.query.get.return_value = mock_attachment
        
        mock_hash.return_value = "abc123" * 10 + "def4"  # 64 chars
        
        mock_store = Mock()
        mock_store.check_duplicate_by_hash.return_value = {
            "attachment_id": 99999,
            "chunk_count": 15,
            "content_hash": "abc123" * 10 + "def4"
        }
        mock_store_class.return_value = mock_store
        
        # Act
        result = index_attachment_task(attachment_id=12345, event_id=789)
        
        # Assert
        assert result['status'] == 'skipped'
        assert result['success'] is True
        assert result['chunks_created'] == 0
        assert result['chunks_skipped'] == 15
        assert result['content_hash'] == "abc123" * 10 + "def4"
    
    @patch('indico_assistant.tasks.indexing.Attachment')
    def test_task_returns_failed_for_missing_attachment(
        self,
        mock_attachment_class
    ):
        """Test that task returns 'failed' when attachment not found.
        
        Task: T013
        Contract: indexing_task.yaml error scenario - attachment deleted
        """
        # Arrange
        from indico_assistant.tasks.indexing import index_attachment_task
        
        mock_attachment_class.query.get.return_value = None
        
        # Act
        result = index_attachment_task(attachment_id=99999, event_id=789)
        
        # Assert
        assert result['status'] == 'failed'
        assert result['success'] is False
        assert 'not found' in result['error'].lower() or 'deleted' in result['error'].lower()
    
    @patch('indico_assistant.tasks.indexing.Attachment')
    @patch('indico_assistant.tasks.indexing.compute_content_hash')
    @patch('indico_assistant.tasks.indexing.VectorStore')
    @patch('indico_assistant.tasks.indexing.DocumentExtractor')
    @patch('indico_assistant.tasks.indexing.DocumentChunker')
    @patch('indico_assistant.tasks.indexing.EmbeddingService')
    def test_task_returns_indexed_for_new_document(
        self,
        mock_embedding_class,
        mock_chunker_class,
        mock_extractor_class,
        mock_store_class,
        mock_hash,
        mock_attachment_class
    ):
        """Test that task successfully indexes new document.
        
        Task: T013
        FR-004: Extract, chunk, embed, and store within 30s for <10MB
        """
        # Arrange
        from indico_assistant.tasks.indexing import index_attachment_task
        
        mock_attachment = Mock()
        mock_attachment.id = 12345
        mock_attachment.file.size = 5 * 1024 * 1024
        mock_attachment.file.filename = "test.pdf"
        mock_attachment.file.open.return_value.__enter__ = Mock(return_value=BytesIO(b'test content'))
        mock_attachment.file.open.return_value.__exit__ = Mock(return_value=False)
        mock_attachment_class.query.get.return_value = mock_attachment
        
        mock_hash.return_value = "new123" * 10 + "hash"  # 64 chars
        
        mock_store = Mock()
        mock_store.check_duplicate_by_hash.return_value = None  # Not a duplicate
        mock_store.insert_chunks.return_value = 10
        mock_store_class.return_value = mock_store
        
        mock_extractor = Mock()
        mock_extractor.extract_text.return_value = "Extracted text content"
        mock_extractor_class.return_value = mock_extractor
        
        mock_chunker = Mock()
        mock_chunker.chunk_text.return_value = ["chunk1", "chunk2", "chunk3"]
        mock_chunker_class.return_value = mock_chunker
        
        mock_embedder = Mock()
        mock_embedder.embed_texts.return_value = [[0.1] * 384] * 3
        mock_embedding_class.return_value = mock_embedder
        
        # Act
        result = index_attachment_task(attachment_id=12345, event_id=789)
        
        # Assert
        assert result['status'] == 'indexed'
        assert result['success'] is True
        assert result['chunks_created'] == 10
        assert result['chunks_skipped'] == 0
        assert result['content_hash'] == "new123" * 10 + "hash"
        assert result['attachment_id'] == 12345
        assert result['event_id'] == 789
    
    @patch('indico_assistant.tasks.indexing.Attachment')
    @patch('indico_assistant.tasks.indexing.compute_content_hash')
    @patch('indico_assistant.tasks.indexing.VectorStore')
    def test_task_bypasses_duplicate_check_when_forced(
        self,
        mock_store_class,
        mock_hash,
        mock_attachment_class
    ):
        """Test that task bypasses duplicate check when force=True.
        
        Task: T013
        Contract: indexing_task.yaml force parameter
        """
        # Arrange
        from indico_assistant.tasks.indexing import index_attachment_task
        
        mock_attachment = Mock()
        mock_attachment.id = 12345
        mock_attachment.file.size = 5 * 1024 * 1024
        mock_attachment.file.open.return_value.__enter__ = Mock(return_value=BytesIO(b'test'))
        mock_attachment.file.open.return_value.__exit__ = Mock(return_value=False)
        mock_attachment_class.query.get.return_value = mock_attachment
        
        mock_hash.return_value = "abc123" * 10 + "def4"
        
        mock_store = Mock()
        mock_store.check_duplicate_by_hash.return_value = {
            "attachment_id": 99999,
            "chunk_count": 15,
            "content_hash": "abc123" * 10 + "def4"
        }
        mock_store_class.return_value = mock_store
        
        # Act with force=True
        result = index_attachment_task(attachment_id=12345, event_id=789, force=True)
        
        # Assert - should NOT skip even though duplicate exists
        mock_store.check_duplicate_by_hash.assert_not_called()
