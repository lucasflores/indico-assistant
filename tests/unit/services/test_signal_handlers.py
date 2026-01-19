"""Unit tests for signal handler in real-time indexing.

Feature: 011-realtime-attachment-indexing
Tasks: T012, T013, T015
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from indico_assistant.models.document import ProcessingTier


class TestSignalHandler:
    """Tests for _on_attachment_created signal handler."""
    
    @patch('indico_assistant.plugin.check_pgvector_available')
    @patch('indico_assistant.plugin.index_attachment_task')
    def test_signal_handler_queues_task_for_supported_file(
        self, 
        mock_task, 
        mock_pgvector,
        assistant_plugin
    ):
        """Test that signal handler queues task for supported PDF file.
        
        Task: T012 - Unit test for signal handler
        FR-001: Queue task within 1s for supported documents
        """
        # Arrange
        mock_pgvector.return_value = True
        assistant_plugin.settings.set('vector_search_enabled', True)
        
        attachment = Mock()
        attachment.id = 12345
        attachment.file.filename = "document.pdf"
        attachment.file.size = 5 * 1024 * 1024  # 5MB
        attachment.folder.event.id = 789
        
        # Act
        assistant_plugin._on_attachment_created(sender=None, attachment=attachment)
        
        # Assert
        mock_task.apply_async.assert_called_once()
        call_args = mock_task.apply_async.call_args
        assert call_args[1]['args'] == [12345, 789]
        assert call_args[1]['kwargs']['force'] is False
        assert call_args[1]['priority'] == 5  # FAST tier
    
    @patch('indico_assistant.plugin.check_pgvector_available')
    @patch('indico_assistant.plugin.index_attachment_task')
    def test_signal_handler_skips_unsupported_format(
        self, 
        mock_task, 
        mock_pgvector,
        assistant_plugin
    ):
        """Test that signal handler skips unsupported file formats.
        
        Task: T012
        FR-012: Ignore unsupported file types
        """
        # Arrange
        mock_pgvector.return_value = True
        assistant_plugin.settings.set('vector_search_enabled', True)
        
        attachment = Mock()
        attachment.id = 12345
        attachment.file.filename = "image.jpg"
        attachment.file.size = 2 * 1024 * 1024
        attachment.folder.event.id = 789
        
        # Act
        assistant_plugin._on_attachment_created(sender=None, attachment=attachment)
        
        # Assert
        mock_task.apply_async.assert_not_called()
    
    @patch('indico_assistant.plugin.check_pgvector_available')
    @patch('indico_assistant.plugin.index_attachment_task')
    def test_signal_handler_rejects_large_files(
        self, 
        mock_task, 
        mock_pgvector,
        assistant_plugin
    ):
        """Test that signal handler rejects files over 50MB.
        
        Task: T012
        FR-003: Files >50MB are rejected
        """
        # Arrange
        mock_pgvector.return_value = True
        assistant_plugin.settings.set('vector_search_enabled', True)
        
        attachment = Mock()
        attachment.id = 12345
        attachment.file.filename = "large.pdf"
        attachment.file.size = 100 * 1024 * 1024  # 100MB
        attachment.folder.event.id = 789
        
        # Act
        assistant_plugin._on_attachment_created(sender=None, attachment=attachment)
        
        # Assert
        mock_task.apply_async.assert_not_called()
    
    @patch('indico_assistant.plugin.check_pgvector_available')
    @patch('indico_assistant.plugin.index_attachment_task')
    def test_signal_handler_uses_low_priority_for_large_files(
        self, 
        mock_task, 
        mock_pgvector,
        assistant_plugin
    ):
        """Test that signal handler uses priority 9 for BEST_EFFORT tier.
        
        Task: T012
        FR-003: Files 10-50MB indexed with lower priority
        """
        # Arrange
        mock_pgvector.return_value = True
        assistant_plugin.settings.set('vector_search_enabled', True)
        
        attachment = Mock()
        attachment.id = 12345
        attachment.file.filename = "medium.pdf"
        attachment.file.size = 30 * 1024 * 1024  # 30MB
        attachment.folder.event.id = 789
        
        # Act
        assistant_plugin._on_attachment_created(sender=None, attachment=attachment)
        
        # Assert
        mock_task.apply_async.assert_called_once()
        call_args = mock_task.apply_async.call_args
        assert call_args[1]['priority'] == 9  # BEST_EFFORT tier
    
    @patch('indico_assistant.plugin.check_pgvector_available')
    @patch('indico_assistant.plugin.index_attachment_task')
    def test_signal_handler_skips_when_vector_search_disabled(
        self, 
        mock_task, 
        mock_pgvector,
        assistant_plugin
    ):
        """Test that signal handler skips when vector search disabled.
        
        Task: T012
        FR-002: Check vector search enabled before queueing
        """
        # Arrange
        mock_pgvector.return_value = True
        assistant_plugin.settings.set('vector_search_enabled', False)
        
        attachment = Mock()
        attachment.id = 12345
        attachment.file.filename = "document.pdf"
        attachment.file.size = 5 * 1024 * 1024
        attachment.folder.event.id = 789
        
        # Act
        assistant_plugin._on_attachment_created(sender=None, attachment=attachment)
        
        # Assert
        mock_task.apply_async.assert_not_called()
    
    @patch('indico_assistant.plugin.check_pgvector_available')
    @patch('indico_assistant.plugin.index_attachment_task')
    def test_signal_handler_skips_when_pgvector_unavailable(
        self, 
        mock_task, 
        mock_pgvector,
        assistant_plugin
    ):
        """Test that signal handler skips when pgvector unavailable.
        
        Task: T012
        FR-011: Gracefully handle pgvector unavailability
        """
        # Arrange
        mock_pgvector.return_value = False
        assistant_plugin.settings.set('vector_search_enabled', True)
        
        attachment = Mock()
        attachment.id = 12345
        attachment.file.filename = "document.pdf"
        attachment.file.size = 5 * 1024 * 1024
        attachment.folder.event.id = 789
        
        # Act
        assistant_plugin._on_attachment_created(sender=None, attachment=attachment)
        
        # Assert
        mock_task.apply_async.assert_not_called()
    
    @patch('indico_assistant.plugin.check_pgvector_available')
    @patch('indico_assistant.plugin.index_attachment_task')
    def test_signal_handler_never_raises_exceptions(
        self, 
        mock_task, 
        mock_pgvector,
        assistant_plugin
    ):
        """Test that signal handler catches all exceptions.
        
        Task: T012
        FR-009: Handler must complete in <100ms, never block
        """
        # Arrange
        mock_pgvector.side_effect = Exception("Database error")
        assistant_plugin.settings.set('vector_search_enabled', True)
        
        attachment = Mock()
        attachment.id = 12345
        attachment.file.filename = "document.pdf"
        attachment.file.size = 5 * 1024 * 1024
        attachment.folder.event.id = 789
        
        # Act & Assert - should not raise
        assistant_plugin._on_attachment_created(sender=None, attachment=attachment)
    
    @patch('indico_assistant.plugin.check_pgvector_available')
    @patch('indico_assistant.plugin.index_attachment_task')
    def test_signal_handler_performance_under_100ms(
        self, 
        mock_task, 
        mock_pgvector,
        assistant_plugin
    ):
        """Test that signal handler completes in under 100ms.
        
        Task: T015 - Performance test for signal handler
        FR-009: Signal handler <100ms (99th percentile)
        SC-002: Handler execution <100ms for 99% of calls
        """
        import time
        
        # Arrange
        mock_pgvector.return_value = True
        assistant_plugin.settings.set('vector_search_enabled', True)
        
        attachment = Mock()
        attachment.id = 12345
        attachment.file.filename = "document.pdf"
        attachment.file.size = 5 * 1024 * 1024
        attachment.folder.event.id = 789
        
        # Act
        start = time.perf_counter()
        assistant_plugin._on_attachment_created(sender=None, attachment=attachment)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        # Assert
        assert elapsed_ms < 100, f"Signal handler took {elapsed_ms:.2f}ms (must be <100ms)"


@pytest.fixture
def assistant_plugin():
    """Mock AssistantPlugin instance for testing."""
    plugin = Mock()
    plugin.settings = Mock()
    plugin.settings.get = Mock(return_value=True)
    plugin.settings.set = Mock()
    return plugin
