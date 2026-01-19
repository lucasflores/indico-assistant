"""Integration tests for unsupported file format handling.

Feature: 011-realtime-attachment-indexing
Tasks: T032
"""

import pytest
import time
from io import BytesIO


class TestUnsupportedFormatHandling:
    """Integration tests for graceful handling of unsupported file formats."""
    
    @pytest.mark.integration
    def test_image_upload_creates_no_vector_entries(
        self,
        db,
        create_event,
        create_attachment,
        vector_store
    ):
        """Test that uploading an image file does not create vector entries.
        
        Task: T032 - Integration test for mixed uploads
        US2: Silently ignore JPG/PNG/MP4 etc.
        FR-012: Ignore unsupported file formats
        """
        # Arrange
        event = create_event(title="Test Event")
        
        # Create an image attachment
        image_content = b"FAKE_JPG_DATA"
        attachment = create_attachment(
            event=event,
            filename="photo.jpg",
            content=BytesIO(image_content),
            content_type="image/jpeg"
        )
        
        # Act - wait for potential indexing attempt
        time.sleep(2)
        
        # Assert - no vector entries should exist for this attachment
        chunks = vector_store.get_chunks_by_attachment(attachment.id)
        assert len(chunks) == 0, "Image file should not be indexed"
    
    @pytest.mark.integration
    def test_video_upload_creates_no_vector_entries(
        self,
        db,
        create_event,
        create_attachment,
        vector_store
    ):
        """Test that uploading a video file does not create vector entries.
        
        Task: T032
        US2: Gracefully ignore unsupported formats
        """
        # Arrange
        event = create_event(title="Test Event")
        
        video_content = b"FAKE_MP4_DATA"
        attachment = create_attachment(
            event=event,
            filename="presentation.mp4",
            content=BytesIO(video_content),
            content_type="video/mp4"
        )
        
        # Act
        time.sleep(2)
        
        # Assert
        chunks = vector_store.get_chunks_by_attachment(attachment.id)
        assert len(chunks) == 0, "Video file should not be indexed"
    
    @pytest.mark.integration
    def test_mixed_upload_indexes_only_supported_formats(
        self,
        db,
        create_event,
        create_attachment,
        vector_store
    ):
        """Test that uploading mixed file types indexes only supported formats.
        
        Task: T032
        US2: Mixed uploads should process PDF but ignore image
        """
        # Arrange
        event = create_event(title="Test Conference")
        
        # Upload PDF (supported)
        pdf_content = b"%PDF-1.4\nSupported document content."
        pdf_attachment = create_attachment(
            event=event,
            filename="document.pdf",
            content=BytesIO(pdf_content),
            content_type="application/pdf"
        )
        
        # Upload image (unsupported)
        image_content = b"FAKE_PNG_DATA"
        image_attachment = create_attachment(
            event=event,
            filename="diagram.png",
            content=BytesIO(image_content),
            content_type="image/png"
        )
        
        # Upload text (supported)
        txt_content = b"Plain text document."
        txt_attachment = create_attachment(
            event=event,
            filename="notes.txt",
            content=BytesIO(txt_content),
            content_type="text/plain"
        )
        
        # Act - wait for indexing
        time.sleep(8)
        
        # Assert - only PDF and TXT should be indexed
        pdf_chunks = vector_store.get_chunks_by_attachment(pdf_attachment.id)
        assert len(pdf_chunks) > 0, "PDF should be indexed"
        
        image_chunks = vector_store.get_chunks_by_attachment(image_attachment.id)
        assert len(image_chunks) == 0, "PNG should not be indexed"
        
        txt_chunks = vector_store.get_chunks_by_attachment(txt_attachment.id)
        assert len(txt_chunks) > 0, "TXT should be indexed"
    
    @pytest.mark.integration
    def test_unsupported_upload_does_not_raise_errors(
        self,
        db,
        create_event,
        create_attachment
    ):
        """Test that uploading unsupported formats does not raise errors.
        
        Task: T032
        US2: No user-visible errors for unsupported formats
        FR-011: Graceful degradation
        """
        # Arrange
        event = create_event(title="Test Event")
        
        # Act - upload various unsupported formats
        formats = [
            ("archive.zip", "application/zip"),
            ("audio.mp3", "audio/mpeg"),
            ("script.py", "text/x-python"),
            ("data.csv", "text/csv"),
            ("spreadsheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        ]
        
        for filename, content_type in formats:
            try:
                attachment = create_attachment(
                    event=event,
                    filename=filename,
                    content=BytesIO(b"test data"),
                    content_type=content_type
                )
                # Should not raise any exceptions
            except Exception as e:
                pytest.fail(f"Upload of {filename} raised exception: {e}")
        
        # Wait for potential processing
        time.sleep(2)
        
        # No assertions needed - test passes if no exceptions were raised
