"""Unit tests for document validation helpers.

Feature: 011-realtime-attachment-indexing
Tasks: T031
"""

import pytest
from indico_assistant.services.document.validation import (
    is_supported_format,
    determine_processing_tier
)
from indico_assistant.models.document import ProcessingTier


class TestFormatValidation:
    """Tests for file format validation."""
    
    def test_is_supported_format_accepts_pdf(self):
        """Test that PDF files are recognized as supported.
        
        Task: T031 - Unit test for format validation
        FR-012: Support PDF, DOCX, DOC, TXT, MD formats
        """
        assert is_supported_format("document.pdf") is True
        assert is_supported_format("REPORT.PDF") is True
        assert is_supported_format("file.Pdf") is True
    
    def test_is_supported_format_accepts_docx(self):
        """Test that DOCX files are recognized as supported."""
        assert is_supported_format("document.docx") is True
        assert is_supported_format("REPORT.DOCX") is True
    
    def test_is_supported_format_accepts_doc(self):
        """Test that DOC files are recognized as supported."""
        assert is_supported_format("document.doc") is True
        assert is_supported_format("REPORT.DOC") is True
    
    def test_is_supported_format_accepts_txt(self):
        """Test that TXT files are recognized as supported."""
        assert is_supported_format("notes.txt") is True
        assert is_supported_format("README.TXT") is True
    
    def test_is_supported_format_accepts_markdown(self):
        """Test that Markdown files are recognized as supported."""
        assert is_supported_format("readme.md") is True
        assert is_supported_format("CHANGELOG.MD") is True
    
    def test_is_supported_format_rejects_images(self):
        """Test that image files are rejected.
        
        Task: T031
        US2: Gracefully ignore unsupported formats
        """
        assert is_supported_format("photo.jpg") is False
        assert is_supported_format("image.jpeg") is False
        assert is_supported_format("picture.png") is False
        assert is_supported_format("graphic.gif") is False
        assert is_supported_format("vector.svg") is False
    
    def test_is_supported_format_rejects_videos(self):
        """Test that video files are rejected."""
        assert is_supported_format("video.mp4") is False
        assert is_supported_format("movie.avi") is False
        assert is_supported_format("clip.mov") is False
        assert is_supported_format("recording.mkv") is False
    
    def test_is_supported_format_rejects_audio(self):
        """Test that audio files are rejected."""
        assert is_supported_format("audio.mp3") is False
        assert is_supported_format("song.wav") is False
        assert is_supported_format("podcast.m4a") is False
    
    def test_is_supported_format_rejects_archives(self):
        """Test that archive files are rejected."""
        assert is_supported_format("archive.zip") is False
        assert is_supported_format("package.tar.gz") is False
        assert is_supported_format("backup.rar") is False
    
    def test_is_supported_format_rejects_executables(self):
        """Test that executable files are rejected."""
        assert is_supported_format("program.exe") is False
        assert is_supported_format("script.sh") is False
        assert is_supported_format("binary.bin") is False
    
    def test_is_supported_format_handles_no_extension(self):
        """Test that files without extension are rejected."""
        assert is_supported_format("README") is False
        assert is_supported_format("LICENSE") is False
    
    def test_is_supported_format_handles_multiple_dots(self):
        """Test that files with multiple dots are handled correctly."""
        assert is_supported_format("archive.tar.gz") is False
        assert is_supported_format("document.final.pdf") is True
        assert is_supported_format("notes.backup.txt") is True


class TestProcessingTierDetermination:
    """Tests for file size tier determination."""
    
    def test_determine_tier_fast_for_small_files(self):
        """Test that files <10MB are assigned FAST tier.
        
        Task: T031
        FR-004: <10MB files indexed within 30s (FAST tier)
        """
        # 1MB file
        assert determine_processing_tier(1 * 1024 * 1024) == ProcessingTier.FAST
        
        # 5MB file
        assert determine_processing_tier(5 * 1024 * 1024) == ProcessingTier.FAST
        
        # 9.99MB file (just under limit)
        assert determine_processing_tier(int(9.99 * 1024 * 1024)) == ProcessingTier.FAST
    
    def test_determine_tier_best_effort_for_medium_files(self):
        """Test that files 10-50MB are assigned BEST_EFFORT tier.
        
        Task: T031
        FR-008: 10-50MB files indexed without time guarantee (BEST_EFFORT tier)
        """
        # 10MB file (exactly at boundary)
        assert determine_processing_tier(10 * 1024 * 1024) == ProcessingTier.BEST_EFFORT
        
        # 25MB file
        assert determine_processing_tier(25 * 1024 * 1024) == ProcessingTier.BEST_EFFORT
        
        # 49.99MB file (just under max)
        assert determine_processing_tier(int(49.99 * 1024 * 1024)) == ProcessingTier.BEST_EFFORT
    
    def test_determine_tier_rejected_for_large_files(self):
        """Test that files >50MB are assigned REJECTED tier.
        
        Task: T031
        FR-003: Reject files exceeding MAX_FILE_SIZE_MB (default 50MB)
        """
        # 50MB file (exactly at boundary)
        assert determine_processing_tier(50 * 1024 * 1024) == ProcessingTier.REJECTED
        
        # 51MB file
        assert determine_processing_tier(51 * 1024 * 1024) == ProcessingTier.REJECTED
        
        # 100MB file
        assert determine_processing_tier(100 * 1024 * 1024) == ProcessingTier.REJECTED
    
    def test_determine_tier_handles_zero_size(self):
        """Test that zero-size files are assigned FAST tier."""
        assert determine_processing_tier(0) == ProcessingTier.FAST
    
    def test_determine_tier_handles_tiny_files(self):
        """Test that tiny files (<1KB) are assigned FAST tier."""
        # 100 bytes
        assert determine_processing_tier(100) == ProcessingTier.FAST
        
        # 1KB
        assert determine_processing_tier(1024) == ProcessingTier.FAST
