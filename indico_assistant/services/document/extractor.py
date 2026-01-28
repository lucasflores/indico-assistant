"""Document text extraction for various file formats.

Feature: 006-vector-search-rag
Tasks: T016, T017, T018, T019

Provides text extraction from PDF, DOCX, TXT, and MD files.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import BinaryIO, Optional, Union

logger = logging.getLogger(__name__)


def _sanitize_text(text: str) -> str:
    """Remove NULL bytes and non-printable characters from text.
    
    PostgreSQL cannot store NULL bytes (0x00) in text fields.
    This function removes them along with other non-printable characters.
    
    Args:
        text: Raw extracted text.
        
    Returns:
        Sanitized text safe for database storage.
    """
    # Use isprintable() to filter out non-printable characters including NULL bytes
    return ''.join(char for char in text if char.isprintable())


class ExtractionError(Exception):
    """Raised when document extraction fails."""
    pass


class UnsupportedFileTypeError(ExtractionError):
    """Raised when file type is not supported."""
    pass


class DocumentExtractor:
    """Extracts text from various document formats.
    
    Supported formats:
    - PDF: Uses PyPDF2 for text extraction
    - DOCX/DOC: Uses python-docx for text extraction
    - TXT/MD: Plain text reading
    
    Example:
        >>> extractor = DocumentExtractor()
        >>> text = extractor.extract("/path/to/document.pdf")
        >>> text, metadata = extractor.extract_with_metadata("/path/to/doc.docx")
    """
    
    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt', '.md'}
    
    def __init__(self, supported_extensions: Optional[list[str]] = None) -> None:
        """Initialize the document extractor.
        
        Args:
            supported_extensions: Optional list of supported extensions.
                Defaults to SUPPORTED_EXTENSIONS class attribute.
        """
        if supported_extensions:
            self._extensions = {ext.lower() for ext in supported_extensions}
        else:
            self._extensions = self.SUPPORTED_EXTENSIONS
    
    def is_supported(self, file_path: Union[str, Path]) -> bool:
        """Check if file type is supported.
        
        Args:
            file_path: Path to the file.
            
        Returns:
            True if file type is supported for extraction.
        """
        ext = Path(file_path).suffix.lower()
        return ext in self._extensions
    
    def extract(self, file_path: Union[str, Path]) -> str:
        """Extract text from a document file.
        
        Args:
            file_path: Path to the document file.
            
        Returns:
            Extracted text content.
            
        Raises:
            UnsupportedFileTypeError: If file type is not supported.
            ExtractionError: If extraction fails.
            FileNotFoundError: If file does not exist.
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        ext = path.suffix.lower()
        
        if ext not in self._extensions:
            raise UnsupportedFileTypeError(
                f"Unsupported file type: {ext}. "
                f"Supported: {', '.join(sorted(self._extensions))}"
            )
        
        try:
            if ext == '.pdf':
                text = self._extract_pdf(path)
            elif ext in {'.docx', '.doc'}:
                text = self._extract_docx(path)
            elif ext in {'.txt', '.md'}:
                text = self._extract_text(path)
            else:
                raise UnsupportedFileTypeError(f"No extractor for: {ext}")
            
            # Sanitize text to remove NULL bytes and problematic characters
            return _sanitize_text(text)
        except (UnsupportedFileTypeError, FileNotFoundError):
            raise
        except Exception as e:
            raise ExtractionError(f"Failed to extract text from {file_path}: {e}")
    
    def extract_with_metadata(
        self, 
        file_path: Union[str, Path]
    ) -> tuple[str, dict]:
        """Extract text and metadata from a document file.
        
        Args:
            file_path: Path to the document file.
            
        Returns:
            Tuple of (extracted_text, metadata_dict).
            
        Raises:
            UnsupportedFileTypeError: If file type is not supported.
            ExtractionError: If extraction fails.
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        
        text = self.extract(path)
        
        metadata = {
            "filename": path.name,
            "file_type": ext.lstrip('.'),
            "file_size": path.stat().st_size,
            "extraction_method": self._get_extraction_method(ext),
        }
        
        # Add format-specific metadata
        if ext == '.pdf':
            try:
                pdf_meta = self._get_pdf_metadata(path)
                metadata.update(pdf_meta)
            except Exception as e:
                logger.warning(f"Could not extract PDF metadata: {e}")
        
        return text, metadata
    
    def _extract_pdf(self, file_path: Path) -> str:
        """Extract text from PDF file using PyPDF2.
        
        Args:
            file_path: Path to PDF file.
            
        Returns:
            Extracted text content.
        """
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise ExtractionError(
                "PyPDF2 not installed. Install with: pip install PyPDF2"
            )
        
        try:
            reader = PdfReader(str(file_path))
            text_parts = []
            
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"PDF extraction failed for {file_path}: {e}")
            raise ExtractionError(f"PDF extraction failed: {e}")
    
    def _extract_docx(self, file_path: Path) -> str:
        """Extract text from DOCX file using python-docx.
        
        Args:
            file_path: Path to DOCX file.
            
        Returns:
            Extracted text content.
        """
        try:
            from docx import Document
        except ImportError:
            raise ExtractionError(
                "python-docx not installed. Install with: pip install python-docx"
            )
        
        try:
            doc = Document(str(file_path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
            
        except Exception as e:
            logger.error(f"DOCX extraction failed for {file_path}: {e}")
            raise ExtractionError(f"DOCX extraction failed: {e}")
    
    def _extract_text(self, file_path: Path) -> str:
        """Extract text from plain text file.
        
        Args:
            file_path: Path to text file.
            
        Returns:
            File content as text.
        """
        # Try different encodings
        encodings = ['utf-8', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        
        raise ExtractionError(
            f"Could not decode text file with encodings: {encodings}"
        )
    
    def _get_extraction_method(self, ext: str) -> str:
        """Get the extraction method name for a file type.
        
        Args:
            ext: File extension (with or without dot).
            
        Returns:
            Extraction method name.
        """
        ext = ext.lstrip('.')
        methods = {
            'pdf': 'pypdf2',
            'docx': 'python-docx',
            'doc': 'python-docx',
            'txt': 'builtin',
            'md': 'builtin',
        }
        return methods.get(ext, 'unknown')
    
    def _get_pdf_metadata(self, file_path: Path) -> dict:
        """Get PDF-specific metadata.
        
        Args:
            file_path: Path to PDF file.
            
        Returns:
            Dictionary with PDF metadata.
        """
        from PyPDF2 import PdfReader
        
        reader = PdfReader(str(file_path))
        return {
            "total_pages": len(reader.pages),
        }


def extract_text(
    file_path: Union[str, Path],
    supported_extensions: Optional[list[str]] = None
) -> str:
    """Extract text from a document file.
    
    Convenience function that creates a DocumentExtractor and extracts text.
    
    Args:
        file_path: Path to the document file.
        supported_extensions: Optional list of supported extensions.
        
    Returns:
        Extracted text content.
        
    Raises:
        UnsupportedFileTypeError: If file type is not supported.
        ExtractionError: If extraction fails.
    """
    extractor = DocumentExtractor(supported_extensions)
    return extractor.extract(file_path)


def extract_from_bytes(
    content: bytes,
    filename: str,
    supported_extensions: Optional[list[str]] = None
) -> str:
    """Extract text from file content in memory.
    
    Args:
        content: File content as bytes.
        filename: Original filename (used to determine type).
        supported_extensions: Optional list of supported extensions.
        
    Returns:
        Extracted text content.
        
    Raises:
        UnsupportedFileTypeError: If file type is not supported.
        ExtractionError: If extraction fails.
    """
    import tempfile
    
    ext = Path(filename).suffix.lower()
    extractor = DocumentExtractor(supported_extensions)
    
    if ext not in extractor._extensions:
        raise UnsupportedFileTypeError(
            f"Unsupported file type: {ext}"
        )
    
    # Write to temp file and extract
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        return extractor.extract(tmp_path)
    finally:
        os.unlink(tmp_path)
