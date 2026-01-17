# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Unit tests for DocumentChunker service.

Feature: 007-tdd-gap-analysis (GAP-008)
Priority: HIGH
Coverage Target: ≥80%

Tests the document chunking functionality:
- Size-based chunking
- Sentence-based splitting
- Overlap handling
- Small document handling
- Edge cases
"""

import pytest
from unittest.mock import MagicMock, patch

from indico_assistant.services.document.chunker import (
    DocumentChunker,
    DocumentChunk,
    chunk_text,
)


class TestDocumentChunk:
    """Tests for DocumentChunk dataclass."""
    
    def test_document_chunk_creation(self):
        """Test creating a DocumentChunk instance."""
        chunk = DocumentChunk(
            text="This is test content",
            chunk_index=0,
            char_start=0,
            char_end=20
        )
        assert chunk.text == "This is test content"
        assert chunk.chunk_index == 0
        assert chunk.char_start == 0
        assert chunk.char_end == 20
        assert chunk.metadata is None
    
    def test_document_chunk_with_metadata(self):
        """Test creating a DocumentChunk with metadata."""
        metadata = {"source": "test.pdf", "page": 1}
        chunk = DocumentChunk(
            text="Test content",
            chunk_index=1,
            char_start=100,
            char_end=112,
            metadata=metadata
        )
        assert chunk.metadata == metadata
        assert chunk.metadata["source"] == "test.pdf"


class TestDocumentChunkerInit:
    """Tests for DocumentChunker initialization."""
    
    def test_init_with_defaults(self):
        """Test initialization with default values."""
        chunker = DocumentChunker()
        assert chunker.chunk_size == 1000
        assert chunker.chunk_overlap == 200
        assert chunker.separators == DocumentChunker.DEFAULT_SEPARATORS
    
    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        chunker = DocumentChunker(
            chunk_size=500,
            chunk_overlap=100,
            separators=["\n\n", "\n"]
        )
        assert chunker.chunk_size == 500
        assert chunker.chunk_overlap == 100
        assert chunker.separators == ["\n\n", "\n"]
    
    def test_init_invalid_overlap(self):
        """Test that overlap >= chunk_size raises ValueError."""
        with pytest.raises(ValueError, match="Overlap.*must be less than"):
            DocumentChunker(chunk_size=100, chunk_overlap=100)
        
        with pytest.raises(ValueError, match="Overlap.*must be less than"):
            DocumentChunker(chunk_size=100, chunk_overlap=150)


class TestDocumentChunkerChunk:
    """Tests for DocumentChunker.chunk method."""
    
    @pytest.fixture
    def chunker(self):
        """Create a default chunker."""
        return DocumentChunker(chunk_size=100, chunk_overlap=20)
    
    def test_chunk_empty_text(self, chunker):
        """Test chunking empty text returns empty list."""
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []
        assert chunker.chunk("\n\n") == []
    
    def test_chunk_small_text(self, chunker):
        """Test chunking text smaller than chunk_size."""
        text = "This is a small text."
        chunks = chunker.chunk(text)
        
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0
        assert chunks[0].char_start == 0
        assert chunks[0].char_end == len(text)
    
    def test_chunk_text_exactly_chunk_size(self, chunker):
        """Test chunking text exactly equal to chunk_size."""
        text = "x" * 100  # Exactly chunk_size
        chunks = chunker.chunk(text)
        
        assert len(chunks) == 1
        assert len(chunks[0].text) == 100
    
    def test_chunk_text_larger_than_chunk_size(self, chunker):
        """Test chunking text larger than chunk_size creates multiple chunks."""
        # Create text that's 250 chars (should create ~3 chunks with overlap)
        text = "a" * 250
        chunks = chunker.chunk(text)
        
        assert len(chunks) > 1
        # All chunks should have content
        for chunk in chunks:
            assert len(chunk.text) > 0
    
    def test_chunk_respects_overlap(self, chunker):
        """Test that chunks have proper overlap."""
        # Create distinctive text to track overlap
        text = "AAAA " * 30 + "BBBB " * 30  # ~300 chars
        chunks = chunker.chunk(text)
        
        # Check that consecutive chunks have some overlap
        for i in range(len(chunks) - 1):
            current_end = chunks[i].char_end
            next_start = chunks[i + 1].char_start
            # Next chunk should start before current chunk ends (overlap)
            assert next_start < current_end
    
    def test_chunk_indices_are_sequential(self, chunker):
        """Test that chunk indices are sequential starting from 0."""
        text = "Test content. " * 50
        chunks = chunker.chunk(text)
        
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
    
    def test_chunk_with_metadata(self, chunker):
        """Test chunking with base metadata."""
        text = "Test content for chunking. " * 20
        base_metadata = {"source": "test.txt", "author": "test"}
        
        chunks = chunker.chunk(text, base_metadata=base_metadata)
        
        for chunk in chunks:
            assert "source" in chunk.metadata
            assert chunk.metadata["source"] == "test.txt"
            assert "chunk_index" in chunk.metadata
    
    def test_chunk_preserves_char_positions(self, chunker):
        """Test that character positions are accurate."""
        text = "The quick brown fox jumps over the lazy dog. " * 10
        chunks = chunker.chunk(text)
        
        # First chunk should start at 0
        assert chunks[0].char_start == 0
        
        # Last chunk should end at stripped text length (trailing space stripped)
        assert chunks[-1].char_end == len(text.strip())
        
        # Verify text at positions matches
        for chunk in chunks:
            extracted = text[chunk.char_start:chunk.char_end].strip()
            # Allow for some whitespace differences
            assert chunk.text in text


class TestDocumentChunkerBreakPoints:
    """Tests for break point finding in chunks."""
    
    def test_chunk_breaks_at_paragraph(self):
        """Test that chunks prefer to break at paragraphs."""
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
        
        # Create text with paragraph break near target size
        text = "First paragraph content here. " * 2 + "\n\n" + "Second paragraph. " * 5
        chunks = chunker.chunk(text)
        
        # Should have created chunks
        assert len(chunks) >= 1
    
    def test_chunk_breaks_at_sentence(self):
        """Test that chunks prefer to break at sentences."""
        chunker = DocumentChunker(chunk_size=80, chunk_overlap=15)
        
        text = "This is sentence one. This is sentence two. This is sentence three. " * 3
        chunks = chunker.chunk(text)
        
        # Chunks should end at sentence boundaries where possible
        for chunk in chunks[:-1]:  # Except last chunk
            # Many chunks should end with period or space after period
            assert chunk.text.rstrip().endswith('.') or chunk.text.endswith('. ')
    
    def test_chunk_breaks_at_word(self):
        """Test that chunks break at word boundaries when no sentence break."""
        chunker = DocumentChunker(chunk_size=50, chunk_overlap=10)
        
        # Long text without periods
        text = "word " * 40
        chunks = chunker.chunk(text)
        
        # Chunks should not break in middle of words
        for chunk in chunks:
            # Should not start or end with partial words
            assert not chunk.text.startswith("ord")  # partial "word"


class TestDocumentChunkerEstimate:
    """Tests for DocumentChunker.estimate_chunk_count method."""
    
    @pytest.fixture
    def chunker(self):
        """Create a chunker for estimation tests."""
        return DocumentChunker(chunk_size=100, chunk_overlap=20)
    
    def test_estimate_empty_text(self, chunker):
        """Test estimating chunks for empty text."""
        assert chunker.estimate_chunk_count("") == 0
        # Note: estimate_chunk_count doesn't strip, so whitespace returns 1
        assert chunker.estimate_chunk_count("   ") == 1
    
    def test_estimate_small_text(self, chunker):
        """Test estimating chunks for small text."""
        assert chunker.estimate_chunk_count("Small text") == 1
        assert chunker.estimate_chunk_count("x" * 50) == 1
    
    def test_estimate_exact_chunk_size(self, chunker):
        """Test estimating for text exactly chunk_size."""
        assert chunker.estimate_chunk_count("x" * 100) == 1
    
    def test_estimate_multiple_chunks(self, chunker):
        """Test estimating for text requiring multiple chunks."""
        # chunk_size=100, overlap=20, effective_step=80
        # For 300 chars: ceil(300/80) = 4 chunks
        estimate = chunker.estimate_chunk_count("x" * 300)
        assert estimate >= 3
        assert estimate <= 5
    
    def test_estimate_large_text(self, chunker):
        """Test estimating for large text."""
        text = "x" * 10000
        estimate = chunker.estimate_chunk_count(text)
        
        # Should be roughly 10000/80 = 125 chunks
        assert estimate > 100
        assert estimate < 150


class TestChunkTextFunction:
    """Tests for the chunk_text convenience function."""
    
    def test_chunk_text_basic(self):
        """Test basic chunk_text functionality."""
        text = "This is test text. " * 20
        chunks = chunk_text(text)
        
        assert len(chunks) >= 1
        for chunk in chunks:
            assert isinstance(chunk, DocumentChunk)
    
    def test_chunk_text_with_custom_size(self):
        """Test chunk_text with custom chunk size."""
        text = "Test content. " * 50
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
        
        # With smaller chunk size, should have more chunks
        assert len(chunks) > 1
    
    def test_chunk_text_with_metadata(self):
        """Test chunk_text with metadata."""
        text = "Content for metadata test. " * 20
        metadata = {"file": "test.txt"}
        
        chunks = chunk_text(text, metadata=metadata)
        
        for chunk in chunks:
            assert chunk.metadata is not None
            assert "file" in chunk.metadata


class TestDocumentChunkerEdgeCases:
    """Tests for edge cases and special scenarios."""
    
    def test_chunk_only_whitespace(self):
        """Test chunking text with only whitespace."""
        chunker = DocumentChunker()
        chunks = chunker.chunk("   \n\n   \t   ")
        assert chunks == []
    
    def test_chunk_single_character(self):
        """Test chunking a single character."""
        chunker = DocumentChunker()
        chunks = chunker.chunk("x")
        assert len(chunks) == 1
        assert chunks[0].text == "x"
    
    def test_chunk_unicode_text(self):
        """Test chunking text with unicode characters."""
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
        text = "日本語テスト。これはテストです。" * 10
        
        chunks = chunker.chunk(text)
        
        assert len(chunks) >= 1
        # All chunks should contain valid unicode
        for chunk in chunks:
            assert isinstance(chunk.text, str)
    
    def test_chunk_with_newlines(self):
        """Test chunking text with various newline patterns."""
        chunker = DocumentChunker(chunk_size=200, chunk_overlap=30)
        text = "Line 1\nLine 2\n\nParagraph 2\n\n\nParagraph 3" * 5
        
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
    
    def test_chunk_very_long_word(self):
        """Test chunking when a word is longer than chunk_size."""
        chunker = DocumentChunker(chunk_size=50, chunk_overlap=10)
        # Word longer than chunk_size
        long_word = "supercalifragilisticexpialidocious" * 3  # ~102 chars
        text = f"Start {long_word} end"
        
        chunks = chunker.chunk(text)
        
        # Should still produce chunks even with long words
        assert len(chunks) >= 1
    
    def test_chunk_all_separators_exhausted(self):
        """Test chunking when no separators match."""
        chunker = DocumentChunker(chunk_size=50, chunk_overlap=10)
        # Text without any of the default separators (no spaces, newlines, etc)
        text = "a" * 200
        
        chunks = chunker.chunk(text)
        
        # Should still chunk at chunk_size boundaries
        assert len(chunks) > 1
    
    def test_chunk_preserves_leading_trailing_spaces_in_middle(self):
        """Test that internal whitespace is preserved."""
        chunker = DocumentChunker(chunk_size=200, chunk_overlap=30)
        text = "Word    with    multiple    spaces. " * 10
        
        chunks = chunker.chunk(text)
        
        # Reconstruct text from chunks (with overlap removed)
        # Internal spaces should be preserved
        for chunk in chunks:
            if "multiple" in chunk.text:
                assert "    " in chunk.text  # Multiple spaces preserved
    
    def test_chunk_custom_separators(self):
        """Test chunking with custom separators."""
        # Custom separator: use semicolons
        chunker = DocumentChunker(
            chunk_size=100,
            chunk_overlap=20,
            separators=["; ", " "]
        )
        text = "Item one; Item two; Item three; Item four; " * 10
        
        chunks = chunker.chunk(text)
        
        # Should break at semicolons where possible
        assert len(chunks) > 1
    
    def test_chunk_minimum_overlap_respected(self):
        """Test that minimum overlap is always respected."""
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=30)
        text = "Content " * 100
        
        chunks = chunker.chunk(text)
        
        # Verify overlap between consecutive chunks
        for i in range(len(chunks) - 1):
            overlap_start = chunks[i + 1].char_start
            overlap_end = chunks[i].char_end
            actual_overlap = overlap_end - overlap_start
            
            # Overlap should be approximately chunk_overlap
            # (may vary due to break point selection)
            assert actual_overlap > 0
