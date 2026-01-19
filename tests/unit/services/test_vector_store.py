"""Unit tests for VectorStore duplicate detection.

Feature: 011-realtime-attachment-indexing
Tasks: T037
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from indico_assistant.services.vector_search.store import VectorStore


class TestVectorStoreDuplicateDetection:
    """Unit tests for hash-based duplicate detection in VectorStore."""
    
    @patch('indico_assistant.services.vector_search.store.db')
    def test_check_duplicate_by_hash_returns_none_for_new_document(self, mock_db):
        """Test that check_duplicate_by_hash returns None for new documents.
        
        Task: T037 - Unit test for duplicate detection
        US3: Duplicate detection logic
        FR-006: Skip re-indexing when content hash matches
        """
        # Arrange
        store = VectorStore()
        
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_db.session.query.return_value = mock_query
        
        # Act
        result = store.check_duplicate_by_hash(
            event_id=123,
            content_hash="new_hash_not_in_db"
        )
        
        # Assert
        assert result is None, "Should return None for new document"
    
    @patch('indico_assistant.services.vector_search.store.db')
    def test_check_duplicate_by_hash_returns_info_for_existing_document(self, mock_db):
        """Test that check_duplicate_by_hash returns info for existing documents.
        
        Task: T037
        US3: Detect duplicate by hash
        """
        # Arrange
        store = VectorStore()
        
        # Mock existing document record
        mock_doc = Mock()
        mock_doc.attachment_id = 99999
        mock_doc.content_hash = "existing_hash_abc123"
        
        # Mock chunk count query
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = mock_doc
        mock_db.session.query.return_value = mock_query
        
        # Mock chunk count (simulating 15 chunks for this document)
        mock_count_query = Mock()
        mock_count_query.filter_by.return_value.count.return_value = 15
        mock_db.session.query.return_value = mock_count_query
        
        # Act
        result = store.check_duplicate_by_hash(
            event_id=123,
            content_hash="existing_hash_abc123"
        )
        
        # Assert
        assert result is not None, "Should return info for existing document"
        assert result['attachment_id'] == 99999
        assert result['content_hash'] == "existing_hash_abc123"
        assert result['chunk_count'] == 15
    
    @patch('indico_assistant.services.vector_search.store.db')
    def test_check_duplicate_by_hash_queries_by_event_and_hash(self, mock_db):
        """Test that check_duplicate_by_hash filters by both event_id and hash.
        
        Task: T037
        US3: Duplicate detection is per-event
        """
        # Arrange
        store = VectorStore()
        
        mock_query = Mock()
        mock_filter_by = Mock()
        mock_query.filter_by.return_value = mock_filter_by
        mock_filter_by.first.return_value = None
        mock_db.session.query.return_value = mock_query
        
        # Act
        store.check_duplicate_by_hash(
            event_id=456,
            content_hash="test_hash_xyz"
        )
        
        # Assert - verify filter_by was called with correct parameters
        mock_query.filter_by.assert_called_once_with(
            event_id=456,
            content_hash="test_hash_xyz"
        )
    
    @patch('indico_assistant.services.vector_search.store.db')
    def test_check_duplicate_by_hash_handles_empty_hash(self, mock_db):
        """Test that check_duplicate_by_hash handles empty hash gracefully.
        
        Task: T037
        """
        # Arrange
        store = VectorStore()
        
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_db.session.query.return_value = mock_query
        
        # Act
        result = store.check_duplicate_by_hash(
            event_id=123,
            content_hash=""
        )
        
        # Assert
        assert result is None, "Empty hash should not match any documents"
    
    @patch('indico_assistant.services.vector_search.store.db')
    def test_check_duplicate_by_hash_distinguishes_different_events(self, mock_db):
        """Test that same hash in different events are treated as separate documents.
        
        Task: T037
        US3: Duplicate detection is per-event, not global
        """
        # Arrange
        store = VectorStore()
        
        # Document exists in event 100 but not in event 200
        def mock_query_func(event_id, content_hash):
            if event_id == 100:
                mock_doc = Mock()
                mock_doc.attachment_id = 555
                mock_doc.content_hash = content_hash
                return mock_doc
            return None
        
        mock_query = Mock()
        mock_query.filter_by.return_value.first.side_effect = [
            mock_query_func(100, "shared_hash"),
            mock_query_func(200, "shared_hash")
        ]
        mock_db.session.query.return_value = mock_query
        
        # Act & Assert - same hash in event 100 should be found
        result_event_100 = store.check_duplicate_by_hash(
            event_id=100,
            content_hash="shared_hash"
        )
        assert result_event_100 is not None, "Should find duplicate in event 100"
        
        # Same hash in event 200 should not be found
        result_event_200 = store.check_duplicate_by_hash(
            event_id=200,
            content_hash="shared_hash"
        )
        assert result_event_200 is None, "Should not find duplicate in event 200"
