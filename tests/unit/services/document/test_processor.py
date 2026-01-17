# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Unit tests for DocumentProcessor service.

Feature: 007-tdd-gap-analysis (GAP-007)
Priority: HIGH
Coverage Target: ≥80%

Tests the document processing pipeline:
- File processing (PDF, text, HTML)
- Content processing from bytes
- Error handling and edge cases
- Integration with extractor, chunker, embedding service
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from indico_assistant.services.document.processor import (
    DocumentProcessor,
    ProcessingResult,
)
from indico_assistant.services.document.extractor import (
    ExtractionError,
    UnsupportedFileTypeError,
)
from indico_assistant.services.document.chunker import DocumentChunk


class TestProcessingResult:
    """Tests for ProcessingResult dataclass."""
    
    def test_success_result(self):
        """Test creating a successful processing result."""
        result = ProcessingResult(
            success=True,
            attachment_id=123,
            chunks_created=5
        )
        assert result.success is True
        assert result.attachment_id == 123
        assert result.chunks_created == 5
        assert result.error is None
        assert result.skipped is False
    
    def test_skipped_result(self):
        """Test creating a skipped processing result."""
        result = ProcessingResult(
            success=True,
            attachment_id=456,
            skipped=True,
            error="Unsupported file type"
        )
        assert result.success is True
        assert result.skipped is True
        assert result.error == "Unsupported file type"
        assert result.chunks_created == 0
    
    def test_failed_result(self):
        """Test creating a failed processing result."""
        result = ProcessingResult(
            success=False,
            attachment_id=789,
            error="Extraction failed"
        )
        assert result.success is False
        assert result.error == "Extraction failed"
        assert result.chunks_created == 0


class TestDocumentProcessorInit:
    """Tests for DocumentProcessor initialization."""
    
    def test_init_with_required_args(self):
        """Test initialization with required arguments."""
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        
        processor = DocumentProcessor(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store
        )
        
        assert processor._embedding_service == mock_embedding_service
        assert processor._vector_store == mock_vector_store
        # Check defaults
        assert processor._chunker.chunk_size == 1000
        assert processor._chunker.chunk_overlap == 200
    
    def test_init_with_custom_chunk_settings(self):
        """Test initialization with custom chunk settings."""
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        
        processor = DocumentProcessor(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
            chunk_size=500,
            chunk_overlap=100
        )
        
        assert processor._chunker.chunk_size == 500
        assert processor._chunker.chunk_overlap == 100
    
    def test_init_with_custom_extensions(self):
        """Test initialization with custom supported extensions."""
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        
        processor = DocumentProcessor(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
            supported_extensions=['.pdf', '.txt']
        )
        
        assert processor._extractor.is_supported(Path("test.pdf"))
        assert processor._extractor.is_supported(Path("test.txt"))
        assert not processor._extractor.is_supported(Path("test.docx"))


class TestDocumentProcessorProcessFile:
    """Tests for DocumentProcessor.process_file method."""
    
    @pytest.fixture
    def processor(self):
        """Create a processor with mocked dependencies."""
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        mock_vector_store.get_content_hash.return_value = None
        
        processor = DocumentProcessor(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store
        )
        return processor
    
    def test_process_unsupported_file_type(self, processor, tmp_path):
        """Test processing an unsupported file type."""
        # Create a file with unsupported extension
        unsupported_file = tmp_path / "test.xyz"
        unsupported_file.write_text("content")
        
        result = processor.process_file(
            file_path=unsupported_file,
            event_id=1,
            attachment_id=100
        )
        
        assert result.success is True
        assert result.skipped is True
        assert ".xyz" in result.error
    
    def test_process_text_file_success(self, processor, tmp_path):
        """Test successful processing of a text file."""
        # Create a text file
        text_file = tmp_path / "test.txt"
        text_file.write_text("This is test content for processing. " * 50)
        
        # Mock embedding service
        processor._embedding_service.embed_batch.return_value = [[0.1] * 384]
        processor._vector_store.insert_chunks.return_value = 1
        
        result = processor.process_file(
            file_path=text_file,
            event_id=1,
            attachment_id=100
        )
        
        assert result.success is True
        assert result.skipped is False
        assert result.chunks_created >= 1
        processor._vector_store.insert_chunks.assert_called_once()
    
    def test_process_file_no_text_content(self, processor, tmp_path):
        """Test processing a file with no text content."""
        # Create an empty text file
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("   ")  # whitespace only
        
        result = processor.process_file(
            file_path=empty_file,
            event_id=1,
            attachment_id=100
        )
        
        assert result.success is True
        assert result.skipped is True
        assert "No text content" in result.error
    
    def test_process_file_content_unchanged(self, processor, tmp_path):
        """Test skipping when content hash matches."""
        text_file = tmp_path / "test.txt"
        content = "This is test content"
        text_file.write_text(content)
        
        # Mock that content hash already exists
        from indico_assistant.services.embedding.cache import compute_content_hash
        existing_hash = compute_content_hash(content)
        processor._vector_store.get_content_hash.return_value = existing_hash
        
        result = processor.process_file(
            file_path=text_file,
            event_id=1,
            attachment_id=100
        )
        
        assert result.success is True
        assert result.skipped is True
        assert "unchanged" in result.error.lower()
    
    def test_process_file_force_reprocess(self, processor, tmp_path):
        """Test force reprocessing when content unchanged."""
        text_file = tmp_path / "test.txt"
        content = "This is test content for forced reprocessing. " * 30
        text_file.write_text(content)
        
        # Mock that content hash exists
        from indico_assistant.services.embedding.cache import compute_content_hash
        existing_hash = compute_content_hash(content)
        processor._vector_store.get_content_hash.return_value = existing_hash
        
        # Mock embedding service
        processor._embedding_service.embed_batch.return_value = [[0.1] * 384]
        processor._vector_store.insert_chunks.return_value = 1
        
        result = processor.process_file(
            file_path=text_file,
            event_id=1,
            attachment_id=100,
            force=True
        )
        
        assert result.success is True
        assert result.skipped is False
        processor._vector_store.delete_attachment_chunks.assert_called_once_with(100)
    
    def test_process_file_extraction_error(self, processor, tmp_path):
        """Test handling of extraction errors."""
        # Create a valid extension but corrupt content
        pdf_file = tmp_path / "corrupt.pdf"
        pdf_file.write_bytes(b"not a valid pdf")
        
        result = processor.process_file(
            file_path=pdf_file,
            event_id=1,
            attachment_id=100
        )
        
        assert result.success is False
        assert result.error is not None
    
    def test_process_file_deletes_existing_chunks(self, processor, tmp_path):
        """Test that existing chunks are deleted before reprocessing."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("Content to process. " * 50)
        
        # Mock embedding service
        processor._embedding_service.embed_batch.return_value = [[0.1] * 384]
        processor._vector_store.insert_chunks.return_value = 1
        
        processor.process_file(
            file_path=text_file,
            event_id=1,
            attachment_id=100
        )
        
        processor._vector_store.delete_attachment_chunks.assert_called_once_with(100)
    
    def test_process_file_no_chunks_generated(self, processor, tmp_path):
        """Test handling when chunker returns no chunks."""
        text_file = tmp_path / "small.txt"
        text_file.write_text("x")  # Very small content
        
        # Mock chunker to return empty list
        with patch.object(processor._chunker, 'chunk', return_value=[]):
            result = processor.process_file(
                file_path=text_file,
                event_id=1,
                attachment_id=100
            )
        
        assert result.success is True
        assert result.skipped is True
        assert "No chunks" in result.error


class TestDocumentProcessorProcessContent:
    """Tests for DocumentProcessor.process_content method."""
    
    @pytest.fixture
    def processor(self):
        """Create a processor with mocked dependencies."""
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        mock_vector_store.get_content_hash.return_value = None
        
        return DocumentProcessor(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store
        )
    
    def test_process_content_text(self, processor):
        """Test processing text content from bytes."""
        content = b"This is test content for byte processing. " * 50
        
        processor._embedding_service.embed_batch.return_value = [[0.1] * 384]
        processor._vector_store.insert_chunks.return_value = 1
        
        result = processor.process_content(
            content=content,
            filename="test.txt",
            event_id=1,
            attachment_id=200
        )
        
        assert result.success is True
        assert result.chunks_created >= 1
    
    def test_process_content_unsupported_type(self, processor):
        """Test processing unsupported content type."""
        content = b"binary data"
        
        result = processor.process_content(
            content=content,
            filename="test.xyz",
            event_id=1,
            attachment_id=200
        )
        
        assert result.success is True
        assert result.skipped is True
    
    def test_process_content_cleans_temp_file(self, processor):
        """Test that temporary file is cleaned up after processing."""
        content = b"Temporary test content. " * 20
        
        processor._embedding_service.embed_batch.return_value = [[0.1] * 384]
        processor._vector_store.insert_chunks.return_value = 1
        
        # Store temp files created
        import tempfile
        original_mkstemp = tempfile.NamedTemporaryFile
        temp_paths = []
        
        def track_temp(*args, **kwargs):
            tmp = original_mkstemp(*args, **kwargs)
            temp_paths.append(tmp.name)
            return tmp
        
        with patch.object(tempfile, 'NamedTemporaryFile', side_effect=track_temp):
            processor.process_content(
                content=content,
                filename="test.txt",
                event_id=1,
                attachment_id=200
            )
        
        # Verify temp file was cleaned up
        for path in temp_paths:
            assert not Path(path).exists()


class TestDocumentProcessorProcessAttachment:
    """Tests for DocumentProcessor.process_attachment method."""
    
    @pytest.fixture
    def processor(self):
        """Create a processor with mocked dependencies."""
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        mock_vector_store.get_content_hash.return_value = None
        
        return DocumentProcessor(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store
        )
    
    def test_process_attachment_no_file(self, processor):
        """Test processing attachment with no file."""
        mock_attachment = MagicMock()
        mock_attachment.file = None
        
        result = processor.process_attachment(
            attachment=mock_attachment,
            event_id=1
        )
        
        assert result["success"] is True
        assert result["skipped"] is True
        assert "No file attached" in result["error"]
    
    def test_process_attachment_file_read_error(self, processor):
        """Test handling file read errors."""
        mock_attachment = MagicMock()
        mock_attachment.id = 123
        mock_attachment.file.open.side_effect = IOError("Cannot read file")
        
        result = processor.process_attachment(
            attachment=mock_attachment,
            event_id=1
        )
        
        assert result["success"] is False
        assert "read file" in result["error"].lower()
    
    def test_process_attachment_success(self, processor):
        """Test successful attachment processing."""
        mock_attachment = MagicMock()
        mock_attachment.id = 123
        mock_attachment.file.filename = "document.txt"
        mock_attachment.file.open.return_value.read.return_value = (
            b"Test document content. " * 50
        )
        
        processor._embedding_service.embed_batch.return_value = [[0.1] * 384]
        processor._vector_store.insert_chunks.return_value = 1
        
        result = processor.process_attachment(
            attachment=mock_attachment,
            event_id=1
        )
        
        assert result["success"] is True
        assert result["chunks_created"] >= 1


class TestDocumentProcessorEdgeCases:
    """Tests for edge cases and error conditions."""
    
    @pytest.fixture
    def processor(self):
        """Create a processor with mocked dependencies."""
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        mock_vector_store.get_content_hash.return_value = None
        
        return DocumentProcessor(
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store
        )
    
    def test_process_file_nonexistent(self, processor):
        """Test processing a nonexistent file."""
        result = processor.process_file(
            file_path="/nonexistent/path/file.txt",
            event_id=1,
            attachment_id=100
        )
        
        assert result.success is False
        assert result.error is not None
    
    def test_process_large_document(self, processor, tmp_path):
        """Test processing a large document creates multiple chunks."""
        # Create a large text file
        text_file = tmp_path / "large.txt"
        large_content = "This is a sentence for testing. " * 1000  # ~32KB
        text_file.write_text(large_content)
        
        # Mock embedding service to return proper number of embeddings
        def mock_embed_batch(texts):
            return [[0.1] * 384 for _ in texts]
        
        processor._embedding_service.embed_batch.side_effect = mock_embed_batch
        processor._vector_store.insert_chunks.return_value = 1
        
        result = processor.process_file(
            file_path=text_file,
            event_id=1,
            attachment_id=100
        )
        
        assert result.success is True
        assert result.chunks_created > 1
    
    def test_process_embedding_service_error(self, processor, tmp_path):
        """Test handling of embedding service errors."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("Test content for embedding. " * 20)
        
        processor._embedding_service.embed_batch.side_effect = Exception(
            "Embedding service unavailable"
        )
        
        result = processor.process_file(
            file_path=text_file,
            event_id=1,
            attachment_id=100
        )
        
        assert result.success is False
        assert "Embedding" in result.error or "embedding" in result.error.lower()
    
    def test_process_vector_store_error(self, processor, tmp_path):
        """Test handling of vector store errors."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("Test content for storage. " * 20)
        
        processor._embedding_service.embed_batch.return_value = [[0.1] * 384]
        processor._vector_store.insert_chunks.side_effect = Exception(
            "Database connection failed"
        )
        
        result = processor.process_file(
            file_path=text_file,
            event_id=1,
            attachment_id=100
        )
        
        assert result.success is False
        assert result.error is not None
    
    def test_process_file_with_unicode_content(self, processor, tmp_path):
        """Test processing file with unicode content."""
        text_file = tmp_path / "unicode.txt"
        unicode_content = "Unicode content: café, naïve, 日本語, 中文, العربية. " * 30
        text_file.write_text(unicode_content, encoding='utf-8')
        
        processor._embedding_service.embed_batch.return_value = [[0.1] * 384]
        processor._vector_store.insert_chunks.return_value = 1
        
        result = processor.process_file(
            file_path=text_file,
            event_id=1,
            attachment_id=100
        )
        
        assert result.success is True
        assert result.chunks_created >= 1
    
    def test_process_file_path_as_string(self, processor, tmp_path):
        """Test that file path can be passed as string."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("String path content. " * 30)
        
        processor._embedding_service.embed_batch.return_value = [[0.1] * 384]
        processor._vector_store.insert_chunks.return_value = 1
        
        # Pass path as string instead of Path object
        result = processor.process_file(
            file_path=str(text_file),
            event_id=1,
            attachment_id=100
        )
        
        assert result.success is True
