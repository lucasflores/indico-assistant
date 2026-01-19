"""Integration tests for duplicate document detection.

Feature: 011-realtime-attachment-indexing
Tasks: T038, T039
"""

import pytest
import time
from io import BytesIO


class TestDuplicateDetection:
    """Integration tests for hash-based duplicate detection."""
    
    @pytest.mark.integration
    def test_duplicate_upload_skips_reindexing(
        self,
        db,
        create_event,
        create_attachment,
        vector_store
    ):
        """Test that uploading same document twice does not re-index.
        
        Task: T038 - Integration test for duplicate upload
        US3: Skip re-indexing when same document uploaded twice
        FR-006: Skip re-indexing when content hash matches
        """
        # Arrange
        event = create_event(title="Test Conference")
        
        pdf_content = b"%PDF-1.4\nUnique document content for duplicate test."
        
        # Upload first copy
        attachment1 = create_attachment(
            event=event,
            filename="original.pdf",
            content=BytesIO(pdf_content),
            content_type="application/pdf"
        )
        
        # Wait for initial indexing
        time.sleep(8)
        
        # Get chunk count after first upload
        chunks_after_first = vector_store.get_chunks_by_attachment(attachment1.id)
        first_chunk_count = len(chunks_after_first)
        
        assert first_chunk_count > 0, "First upload should be indexed"
        
        # Upload second copy with same content
        attachment2 = create_attachment(
            event=event,
            filename="duplicate.pdf",
            content=BytesIO(pdf_content),
            content_type="application/pdf"
        )
        
        # Wait for potential processing
        time.sleep(5)
        
        # Assert - second upload should not create new chunks
        chunks_after_second = vector_store.get_chunks_by_attachment(attachment2.id)
        second_chunk_count = len(chunks_after_second)
        
        assert second_chunk_count == 0, "Duplicate upload should not create new chunks"
        
        # Verify total chunk count in event is unchanged
        all_chunks = vector_store.get_chunks_by_event(event.id)
        assert len(all_chunks) == first_chunk_count, "Total chunks should not increase for duplicate"
    
    @pytest.mark.integration
    def test_modified_content_triggers_reindexing(
        self,
        db,
        create_event,
        create_attachment,
        vector_store
    ):
        """Test that modified document (different hash) triggers new indexing.
        
        Task: T039 - Integration test for modified content
        US3: Different content hash should trigger re-indexing
        FR-006: Hash-based duplicate detection
        """
        # Arrange
        event = create_event(title="Test Conference")
        
        # Upload original version
        original_content = b"%PDF-1.4\nOriginal version of the document."
        attachment1 = create_attachment(
            event=event,
            filename="version1.pdf",
            content=BytesIO(original_content),
            content_type="application/pdf"
        )
        
        # Wait for indexing
        time.sleep(8)
        
        chunks_v1 = vector_store.get_chunks_by_attachment(attachment1.id)
        assert len(chunks_v1) > 0, "Original version should be indexed"
        
        # Upload modified version (different content)
        modified_content = b"%PDF-1.4\nModified version with additional content."
        attachment2 = create_attachment(
            event=event,
            filename="version2.pdf",
            content=BytesIO(modified_content),
            content_type="application/pdf"
        )
        
        # Wait for indexing
        time.sleep(8)
        
        # Assert - modified version should be indexed
        chunks_v2 = vector_store.get_chunks_by_attachment(attachment2.id)
        assert len(chunks_v2) > 0, "Modified version should be indexed (different hash)"
        
        # Verify total chunks increased
        all_chunks = vector_store.get_chunks_by_event(event.id)
        assert len(all_chunks) > len(chunks_v1), "Total chunks should increase for modified content"
    
    @pytest.mark.integration
    def test_duplicate_across_events_indexes_both(
        self,
        db,
        create_event,
        create_attachment,
        vector_store
    ):
        """Test that same document uploaded to different events is indexed for each.
        
        Task: T038
        US3: Duplicate detection is per-event
        """
        # Arrange
        event1 = create_event(title="Conference A")
        event2 = create_event(title="Conference B")
        
        pdf_content = b"%PDF-1.4\nShared document across events."
        
        # Upload to first event
        attachment1 = create_attachment(
            event=event1,
            filename="shared.pdf",
            content=BytesIO(pdf_content),
            content_type="application/pdf"
        )
        
        # Wait for indexing
        time.sleep(8)
        
        chunks_event1 = vector_store.get_chunks_by_attachment(attachment1.id)
        assert len(chunks_event1) > 0, "Document should be indexed for event 1"
        
        # Upload same content to second event
        attachment2 = create_attachment(
            event=event2,
            filename="shared.pdf",
            content=BytesIO(pdf_content),
            content_type="application/pdf"
        )
        
        # Wait for indexing
        time.sleep(8)
        
        # Assert - should be indexed for second event too
        chunks_event2 = vector_store.get_chunks_by_attachment(attachment2.id)
        assert len(chunks_event2) > 0, "Document should be indexed for event 2 (duplicate detection is per-event)"
    
    @pytest.mark.integration
    def test_force_reindex_bypasses_duplicate_check(
        self,
        db,
        create_event,
        create_attachment,
        vector_store
    ):
        """Test that force=True flag bypasses duplicate detection.
        
        Task: T038
        Contract: indexing_task.yaml force parameter
        """
        # Arrange
        event = create_event(title="Test Event")
        
        pdf_content = b"%PDF-1.4\nDocument for force reindex test."
        
        # Upload first time
        attachment = create_attachment(
            event=event,
            filename="document.pdf",
            content=BytesIO(pdf_content),
            content_type="application/pdf"
        )
        
        # Wait for indexing
        time.sleep(8)
        
        chunks_before = vector_store.get_chunks_by_attachment(attachment.id)
        assert len(chunks_before) > 0, "First indexing should create chunks"
        
        # Manually trigger force reindex
        from indico_assistant.tasks.indexing import index_attachment_task
        result = index_attachment_task(
            attachment_id=attachment.id,
            event_id=event.id,
            force=True
        )
        
        # Assert - force reindex should succeed even though content is duplicate
        assert result['success'] is True
        assert result['status'] == 'indexed', "Force reindex should bypass duplicate check"
        assert result['chunks_created'] > 0, "Force reindex should create chunks"
