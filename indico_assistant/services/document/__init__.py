"""Document service package for text extraction and processing.

Feature: 006-vector-search-rag
Task: T013

Provides document text extraction, chunking, and processing.
"""

import logging

logger = logging.getLogger(__name__)

from indico_assistant.services.document.extractor import (
    DocumentExtractor,
    extract_text,
)
from indico_assistant.services.document.chunker import (
    DocumentChunker,
    chunk_text,
)
from indico_assistant.services.document.processor import DocumentProcessor

__all__ = [
    "DocumentExtractor",
    "extract_text",
    "DocumentChunker",
    "chunk_text",
    "DocumentProcessor",
]
