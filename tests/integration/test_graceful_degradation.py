"""Integration tests for graceful degradation when vector search unavailable.

Feature: 011-realtime-attachment-indexing
Tasks: T047
"""

import pytest
import time
from io import BytesIO
from unittest.mock import patch


class TestGracefulDegradation:
    """Integration tests for system behavior when vector search is unavailable."""
    
    @pytest.mark.integration
    @patch('indico_assistant.services.vector_search.VectorStore.is_available')
    def test_upload_succeeds_when_pgvector_unavailable(
        self,
        mock_is_available,
        db,
        create_event,
        create_attachment
    ):
        """Test that document upload succeeds when pgvector is unavailable.
        
        Task: T047 - Integration test for pgvector unavailable
        US4: Don't break uploads when pgvector unavailable
        FR-011: Graceful degradation without user-visible errors
        """
        # Arrange - simulate pgvector unavailable
        mock_is_available.return_value = False
        
        event = create_event(title="Test Event")
        
        pdf_content = b"%PDF-1.4\nDocument content."
        
        # Act - upload should succeed without errors
        try:
            attachment = create_attachment(
                event=event,
                filename="document.pdf",
                content=BytesIO(pdf_content),
                content_type="application/pdf"
            )
        except Exception as e:
            pytest.fail(f"Upload failed when pgvector unavailable: {e}")
        
        # Wait for potential processing attempt
        time.sleep(2)
        
        # Assert - upload succeeded (no exception raised)
        assert attachment is not None
        assert attachment.id is not None
    
    @pytest.mark.integration
    def test_upload_succeeds_when_vector_search_disabled(
        self,
        db,
        create_event,
        create_attachment,
        plugin_settings
    ):
        """Test that document upload succeeds when vector search is disabled.
        
        Task: T047
        US4: Don't break uploads when vector search disabled
        FR-002: Only index when vector search enabled
        """
        # Arrange - disable vector search
        plugin_settings.set('vector_search_enabled', False)
        
        event = create_event(title="Test Event")
        
        pdf_content = b"%PDF-1.4\nDocument content."
        
        # Act - upload should succeed without errors
        try:
            attachment = create_attachment(
                event=event,
                filename="document.pdf",
                content=BytesIO(pdf_content),
                content_type="application/pdf"
            )
        except Exception as e:
            pytest.fail(f"Upload failed when vector search disabled: {e}")
        
        # Wait for potential processing attempt
        time.sleep(2)
        
        # Assert - upload succeeded
        assert attachment is not None
        assert attachment.id is not None
    
    @pytest.mark.integration
    @patch('indico_assistant.services.vector_search.VectorStore.is_available')
    def test_no_indexing_task_queued_when_pgvector_unavailable(
        self,
        mock_is_available,
        db,
        create_event,
        create_attachment,
        celery_inspector
    ):
        """Test that no indexing task is queued when pgvector unavailable.
        
        Task: T047
        US4: Skip indexing attempt when pgvector unavailable
        """
        # Arrange
        mock_is_available.return_value = False
        
        event = create_event(title="Test Event")
        
        pdf_content = b"%PDF-1.4\nDocument content."
        
        # Act
        attachment = create_attachment(
            event=event,
            filename="document.pdf",
            content=BytesIO(pdf_content),
            content_type="application/pdf"
        )
        
        # Wait briefly
        time.sleep(1)
        
        # Assert - no indexing task should be in queue
        active_tasks = celery_inspector.active()
        scheduled_tasks = celery_inspector.scheduled()
        
        indexing_tasks = [
            task for task in (active_tasks + scheduled_tasks)
            if 'index_attachment' in task['name']
        ]
        
        assert len(indexing_tasks) == 0, "No indexing task should be queued when pgvector unavailable"
    
    @pytest.mark.integration
    def test_no_indexing_task_queued_when_vector_search_disabled(
        self,
        db,
        create_event,
        create_attachment,
        plugin_settings,
        celery_inspector
    ):
        """Test that no indexing task is queued when vector search disabled.
        
        Task: T047
        US4: Skip indexing attempt when vector search disabled
        """
        # Arrange
        plugin_settings.set('vector_search_enabled', False)
        
        event = create_event(title="Test Event")
        
        pdf_content = b"%PDF-1.4\nDocument content."
        
        # Act
        attachment = create_attachment(
            event=event,
            filename="document.pdf",
            content=BytesIO(pdf_content),
            content_type="application/pdf"
        )
        
        # Wait briefly
        time.sleep(1)
        
        # Assert - no indexing task should be in queue
        active_tasks = celery_inspector.active()
        scheduled_tasks = celery_inspector.scheduled()
        
        indexing_tasks = [
            task for task in (active_tasks + scheduled_tasks)
            if 'index_attachment' in task['name']
        ]
        
        assert len(indexing_tasks) == 0, "No indexing task should be queued when vector search disabled"
    
    @pytest.mark.integration
    @patch('indico_assistant.services.vector_search.VectorStore.is_available')
    def test_indexing_resumes_when_pgvector_becomes_available(
        self,
        mock_is_available,
        db,
        create_event,
        create_attachment,
        vector_store
    ):
        """Test that indexing resumes when pgvector becomes available again.
        
        Task: T047
        US4: System recovers when vector search becomes available
        """
        # Arrange - pgvector initially unavailable
        mock_is_available.return_value = False
        
        event = create_event(title="Test Event")
        
        pdf_content = b"%PDF-1.4\nDocument content."
        
        # Upload while pgvector unavailable
        attachment = create_attachment(
            event=event,
            filename="document.pdf",
            content=BytesIO(pdf_content),
            content_type="application/pdf"
        )
        
        time.sleep(2)
        
        # Verify no chunks created
        chunks_before = vector_store.get_chunks_by_attachment(attachment.id)
        assert len(chunks_before) == 0, "No chunks should be created while pgvector unavailable"
        
        # Act - pgvector becomes available
        mock_is_available.return_value = True
        
        # Manually trigger indexing (simulating retry or admin action)
        from indico_assistant.tasks.indexing import index_attachment_task
        result = index_attachment_task(
            attachment_id=attachment.id,
            event_id=event.id
        )
        
        # Assert - indexing should succeed now
        assert result['success'] is True
        assert result['status'] == 'indexed'
        
        chunks_after = vector_store.get_chunks_by_attachment(attachment.id)
        assert len(chunks_after) > 0, "Chunks should be created when pgvector available"
