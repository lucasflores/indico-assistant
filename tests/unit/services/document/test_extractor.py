# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Unit tests for DocumentExtractor service.

Feature: 007-tdd-gap-analysis (GAP-009)
Priority: HIGH
Coverage Target: ≥80%

Tests the document extraction functionality:
- PDF extraction
- DOCX extraction
- Plain text extraction
- Metadata extraction
- Error handling for various formats
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, mock_open
import tempfile
import os

from indico_assistant.services.document.extractor import (
    DocumentExtractor,
    ExtractionError,
    UnsupportedFileTypeError,
    extract_text,
    extract_from_bytes,
)


class TestExtractionExceptions:
    """Tests for extraction exception classes."""
    
    def test_extraction_error(self):
        """Test ExtractionError exception."""
        error = ExtractionError("Failed to extract")
        assert str(error) == "Failed to extract"
        assert isinstance(error, Exception)
    
    def test_unsupported_file_type_error(self):
        """Test UnsupportedFileTypeError exception."""
        error = UnsupportedFileTypeError("Unsupported: .xyz")
        assert str(error) == "Unsupported: .xyz"
        assert isinstance(error, ExtractionError)


class TestDocumentExtractorInit:
    """Tests for DocumentExtractor initialization."""
    
    def test_init_with_defaults(self):
        """Test initialization with default extensions."""
        extractor = DocumentExtractor()
        
        assert extractor.is_supported(Path("test.pdf"))
        assert extractor.is_supported(Path("test.docx"))
        assert extractor.is_supported(Path("test.doc"))
        assert extractor.is_supported(Path("test.txt"))
        assert extractor.is_supported(Path("test.md"))
    
    def test_init_with_custom_extensions(self):
        """Test initialization with custom extensions."""
        extractor = DocumentExtractor(supported_extensions=['.pdf', '.txt'])
        
        assert extractor.is_supported(Path("test.pdf"))
        assert extractor.is_supported(Path("test.txt"))
        assert not extractor.is_supported(Path("test.docx"))
        assert not extractor.is_supported(Path("test.md"))
    
    def test_init_extensions_case_insensitive(self):
        """Test that extension matching is case-insensitive."""
        extractor = DocumentExtractor(supported_extensions=['.PDF', '.TXT'])
        
        assert extractor.is_supported(Path("test.pdf"))
        assert extractor.is_supported(Path("test.PDF"))
        assert extractor.is_supported(Path("test.Pdf"))


class TestDocumentExtractorIsSupported:
    """Tests for DocumentExtractor.is_supported method."""
    
    @pytest.fixture
    def extractor(self):
        """Create a default extractor."""
        return DocumentExtractor()
    
    def test_supported_pdf(self, extractor):
        """Test PDF files are supported."""
        assert extractor.is_supported("document.pdf")
        assert extractor.is_supported(Path("document.pdf"))
    
    def test_supported_docx(self, extractor):
        """Test DOCX files are supported."""
        assert extractor.is_supported("document.docx")
        assert extractor.is_supported("document.doc")
    
    def test_supported_text(self, extractor):
        """Test text files are supported."""
        assert extractor.is_supported("file.txt")
        assert extractor.is_supported("README.md")
    
    def test_unsupported_types(self, extractor):
        """Test unsupported file types."""
        assert not extractor.is_supported("image.png")
        assert not extractor.is_supported("video.mp4")
        assert not extractor.is_supported("archive.zip")
        assert not extractor.is_supported("spreadsheet.xlsx")


class TestDocumentExtractorExtract:
    """Tests for DocumentExtractor.extract method."""
    
    @pytest.fixture
    def extractor(self):
        """Create a default extractor."""
        return DocumentExtractor()
    
    def test_extract_nonexistent_file(self, extractor):
        """Test extracting from nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            extractor.extract("/nonexistent/path/file.txt")
    
    def test_extract_unsupported_type(self, extractor, tmp_path):
        """Test extracting unsupported type raises UnsupportedFileTypeError."""
        unsupported = tmp_path / "test.xyz"
        unsupported.write_text("content")
        
        with pytest.raises(UnsupportedFileTypeError) as exc_info:
            extractor.extract(unsupported)
        
        assert ".xyz" in str(exc_info.value)
        assert "Supported:" in str(exc_info.value)
    
    def test_extract_text_file(self, extractor, tmp_path):
        """Test extracting from a text file."""
        text_file = tmp_path / "test.txt"
        content = "This is test content.\nWith multiple lines."
        text_file.write_text(content)
        
        result = extractor.extract(text_file)
        
        assert result == content
    
    def test_extract_markdown_file(self, extractor, tmp_path):
        """Test extracting from a markdown file."""
        md_file = tmp_path / "README.md"
        content = "# Title\n\nSome **bold** text."
        md_file.write_text(content)
        
        result = extractor.extract(md_file)
        
        assert result == content
    
    def test_extract_text_file_utf8(self, extractor, tmp_path):
        """Test extracting UTF-8 encoded text file."""
        text_file = tmp_path / "unicode.txt"
        content = "Unicode: café, naïve, 日本語"
        text_file.write_text(content, encoding='utf-8')
        
        result = extractor.extract(text_file)
        
        assert "café" in result
        assert "日本語" in result
    
    def test_extract_text_file_latin1(self, extractor, tmp_path):
        """Test extracting Latin-1 encoded text file."""
        text_file = tmp_path / "latin1.txt"
        content = "Café résumé"
        text_file.write_bytes(content.encode('latin-1'))
        
        result = extractor.extract(text_file)
        
        assert "Café" in result or "Caf" in result
    
    def test_extract_pdf_missing_library(self, extractor, tmp_path):
        """Test PDF extraction when PyPDF2 not installed."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy")
        
        with patch.dict('sys.modules', {'PyPDF2': None}):
            with patch('builtins.__import__', side_effect=ImportError("No PyPDF2")):
                with pytest.raises(ExtractionError, match="PyPDF2"):
                    extractor.extract(pdf_file)
    
    @patch('indico_assistant.services.document.extractor.DocumentExtractor._extract_pdf')
    def test_extract_pdf_success(self, mock_pdf, extractor, tmp_path):
        """Test successful PDF extraction."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")
        
        mock_pdf.return_value = "Extracted PDF content"
        
        result = extractor.extract(pdf_file)
        
        assert result == "Extracted PDF content"
        mock_pdf.assert_called_once()
    
    @patch('indico_assistant.services.document.extractor.DocumentExtractor._extract_docx')
    def test_extract_docx_success(self, mock_docx, extractor, tmp_path):
        """Test successful DOCX extraction."""
        docx_file = tmp_path / "test.docx"
        docx_file.write_bytes(b"PK content")  # DOCX is a ZIP
        
        mock_docx.return_value = "Extracted DOCX content"
        
        result = extractor.extract(docx_file)
        
        assert result == "Extracted DOCX content"
        mock_docx.assert_called_once()
    
    def test_extract_handles_extraction_error(self, extractor, tmp_path):
        """Test that extraction errors are properly wrapped."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("some content")
        
        # Mock the _extract_text method to simulate all encodings failing
        with patch.object(extractor, '_extract_text') as mock_extract:
            mock_extract.side_effect = ExtractionError("Could not decode text file")
            
            with pytest.raises(ExtractionError, match="Could not decode"):
                extractor.extract(text_file)


class TestDocumentExtractorExtractWithMetadata:
    """Tests for DocumentExtractor.extract_with_metadata method."""
    
    @pytest.fixture
    def extractor(self):
        """Create a default extractor."""
        return DocumentExtractor()
    
    def test_extract_with_metadata_text_file(self, extractor, tmp_path):
        """Test extracting text file with metadata."""
        text_file = tmp_path / "test.txt"
        content = "Test content for metadata extraction."
        text_file.write_text(content)
        
        text, metadata = extractor.extract_with_metadata(text_file)
        
        assert text == content
        assert metadata["filename"] == "test.txt"
        assert metadata["file_type"] == "txt"
        assert metadata["file_size"] > 0
        assert metadata["extraction_method"] == "builtin"
    
    def test_extract_with_metadata_markdown_file(self, extractor, tmp_path):
        """Test extracting markdown file with metadata."""
        md_file = tmp_path / "README.md"
        content = "# Title\n\nContent"
        md_file.write_text(content)
        
        text, metadata = extractor.extract_with_metadata(md_file)
        
        assert metadata["file_type"] == "md"
        assert metadata["extraction_method"] == "builtin"
    
    @patch('indico_assistant.services.document.extractor.DocumentExtractor._extract_pdf')
    @patch('indico_assistant.services.document.extractor.DocumentExtractor._get_pdf_metadata')
    def test_extract_with_metadata_pdf(self, mock_meta, mock_extract, extractor, tmp_path):
        """Test extracting PDF with metadata."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        mock_extract.return_value = "PDF text content"
        mock_meta.return_value = {"total_pages": 5}
        
        text, metadata = extractor.extract_with_metadata(pdf_file)
        
        assert text == "PDF text content"
        assert metadata["file_type"] == "pdf"
        assert metadata["extraction_method"] == "pypdf2"
        assert metadata["total_pages"] == 5
    
    @patch('indico_assistant.services.document.extractor.DocumentExtractor._extract_pdf')
    @patch('indico_assistant.services.document.extractor.DocumentExtractor._get_pdf_metadata')
    def test_extract_with_metadata_pdf_meta_error(self, mock_meta, mock_extract, extractor, tmp_path):
        """Test PDF metadata extraction failure is handled gracefully."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        mock_extract.return_value = "PDF text"
        mock_meta.side_effect = Exception("PDF metadata error")
        
        text, metadata = extractor.extract_with_metadata(pdf_file)
        
        # Should still return text and basic metadata
        assert text == "PDF text"
        assert metadata["file_type"] == "pdf"
        # PDF-specific metadata should not be present
        assert "total_pages" not in metadata


class TestDocumentExtractorPrivateMethods:
    """Tests for private extraction methods."""
    
    @pytest.fixture
    def extractor(self):
        """Create a default extractor."""
        return DocumentExtractor()
    
    def test_get_extraction_method(self, extractor):
        """Test extraction method names are correct."""
        assert extractor._get_extraction_method(".pdf") == "pypdf2"
        assert extractor._get_extraction_method("pdf") == "pypdf2"
        assert extractor._get_extraction_method(".docx") == "python-docx"
        assert extractor._get_extraction_method(".doc") == "python-docx"
        assert extractor._get_extraction_method(".txt") == "builtin"
        assert extractor._get_extraction_method(".md") == "builtin"
        assert extractor._get_extraction_method(".xyz") == "unknown"
    
    def test_extract_text_multiple_encodings(self, extractor, tmp_path):
        """Test text extraction tries multiple encodings."""
        text_file = tmp_path / "test.txt"
        # Write content that's valid in cp1252 but not UTF-8
        text_file.write_bytes(b"Text with special char: \x93quote\x94")
        
        result = extractor._extract_text(text_file)
        
        # Should successfully extract using fallback encoding
        assert "Text" in result


class TestExtractTextFunction:
    """Tests for the extract_text convenience function."""
    
    def test_extract_text_basic(self, tmp_path):
        """Test basic extract_text functionality."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("Convenience function test content")
        
        result = extract_text(text_file)
        
        assert result == "Convenience function test content"
    
    def test_extract_text_with_custom_extensions(self, tmp_path):
        """Test extract_text with custom extensions."""
        # Should work with .txt
        text_file = tmp_path / "test.txt"
        text_file.write_text("Content")
        
        result = extract_text(text_file, supported_extensions=['.txt'])
        assert result == "Content"
        
        # Should fail with .md when not in supported list
        md_file = tmp_path / "test.md"
        md_file.write_text("Markdown")
        
        with pytest.raises(UnsupportedFileTypeError):
            extract_text(md_file, supported_extensions=['.txt'])


class TestExtractFromBytesFunction:
    """Tests for the extract_from_bytes convenience function."""
    
    def test_extract_from_bytes_text(self):
        """Test extracting from text bytes."""
        content = b"Test content from bytes"
        
        result = extract_from_bytes(content, "test.txt")
        
        assert result == "Test content from bytes"
    
    def test_extract_from_bytes_unsupported(self):
        """Test extracting from bytes with unsupported type."""
        content = b"Some content"
        
        with pytest.raises(UnsupportedFileTypeError):
            extract_from_bytes(content, "image.png")
    
    def test_extract_from_bytes_cleans_temp_file(self):
        """Test that temporary file is cleaned up."""
        content = b"Temporary test content"
        
        # Track temp files
        temp_files = []
        original_unlink = os.unlink
        
        def track_unlink(path):
            temp_files.append(path)
            return original_unlink(path)
        
        with patch.object(os, 'unlink', side_effect=track_unlink):
            extract_from_bytes(content, "test.txt")
        
        # Should have deleted the temp file
        assert len(temp_files) == 1
        # File should not exist anymore
        assert not Path(temp_files[0]).exists()
    
    def test_extract_from_bytes_with_custom_extensions(self):
        """Test extract_from_bytes with custom supported extensions."""
        content = b"Markdown content"
        
        # Should fail when .md not in supported
        with pytest.raises(UnsupportedFileTypeError):
            extract_from_bytes(content, "test.md", supported_extensions=['.txt'])
        
        # Should work when .md is supported
        result = extract_from_bytes(content, "test.md", supported_extensions=['.md'])
        assert result == "Markdown content"


class TestDocumentExtractorEdgeCases:
    """Tests for edge cases and error conditions."""
    
    @pytest.fixture
    def extractor(self):
        """Create a default extractor."""
        return DocumentExtractor()
    
    def test_extract_empty_file(self, extractor, tmp_path):
        """Test extracting from empty file."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")
        
        result = extractor.extract(empty_file)
        
        assert result == ""
    
    def test_extract_file_with_path_object(self, extractor, tmp_path):
        """Test extracting using Path object."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("Path object test")
        
        result = extractor.extract(Path(text_file))
        
        assert result == "Path object test"
    
    def test_extract_file_with_string_path(self, extractor, tmp_path):
        """Test extracting using string path."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("String path test")
        
        result = extractor.extract(str(text_file))
        
        assert result == "String path test"
    
    def test_extract_file_with_unicode_path(self, extractor, tmp_path):
        """Test extracting file with unicode in path."""
        unicode_dir = tmp_path / "日本語フォルダ"
        unicode_dir.mkdir()
        text_file = unicode_dir / "文書.txt"
        text_file.write_text("Unicode path content")
        
        result = extractor.extract(text_file)
        
        assert result == "Unicode path content"
    
    def test_extract_very_large_file(self, extractor, tmp_path):
        """Test extracting from a large file."""
        large_file = tmp_path / "large.txt"
        # Create 1MB file
        content = "x" * (1024 * 1024)
        large_file.write_text(content)
        
        result = extractor.extract(large_file)
        
        assert len(result) == 1024 * 1024
    
    def test_is_supported_with_uppercase_extension(self, extractor):
        """Test is_supported handles uppercase extensions."""
        assert extractor.is_supported("FILE.PDF")
        assert extractor.is_supported("FILE.TXT")
        assert extractor.is_supported("FILE.DOCX")
    
    def test_is_supported_with_mixed_case(self, extractor):
        """Test is_supported handles mixed case extensions."""
        assert extractor.is_supported("file.Pdf")
        assert extractor.is_supported("file.TxT")
        assert extractor.is_supported("file.DocX")
    
    @patch('indico_assistant.services.document.extractor.DocumentExtractor._extract_docx')
    def test_extract_doc_extension(self, mock_docx, extractor, tmp_path):
        """Test extracting .doc files uses docx extractor."""
        doc_file = tmp_path / "test.doc"
        doc_file.write_bytes(b"content")
        
        mock_docx.return_value = "DOC content"
        
        result = extractor.extract(doc_file)
        
        assert result == "DOC content"
        mock_docx.assert_called_once()
