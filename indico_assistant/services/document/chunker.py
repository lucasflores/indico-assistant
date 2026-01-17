"""Document chunking for vector search.

Feature: 006-vector-search-rag
Tasks: T020, T021

Provides text chunking with configurable size and overlap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """Represents a chunk of document text.
    
    Attributes:
        text: The chunk text content.
        chunk_index: Position in the sequence of chunks (0-based).
        char_start: Starting character position in original text.
        char_end: Ending character position in original text.
        metadata: Optional additional metadata.
    """
    text: str
    chunk_index: int
    char_start: int
    char_end: int
    metadata: Optional[dict] = None


class DocumentChunker:
    """Splits documents into overlapping chunks for embedding.
    
    The chunker uses a recursive approach that tries to split at
    natural boundaries (paragraphs, sentences) while respecting
    the configured chunk size and overlap.
    
    Attributes:
        chunk_size: Target size for each chunk in characters.
        chunk_overlap: Overlap between consecutive chunks.
        separators: List of separators to try for splitting.
    
    Example:
        >>> chunker = DocumentChunker(chunk_size=1000, overlap=200)
        >>> chunks = chunker.chunk("Long document text...")
        >>> for chunk in chunks:
        ...     print(f"Chunk {chunk.chunk_index}: {len(chunk.text)} chars")
    """
    
    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", ", ", " ", ""]
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Optional[list[str]] = None
    ) -> None:
        """Initialize the document chunker.
        
        Args:
            chunk_size: Target size for each chunk in characters.
                Default: 1000
            chunk_overlap: Overlap between consecutive chunks.
                Default: 200
            separators: List of separators to try for splitting.
                Default: paragraphs, newlines, sentences, words.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS
        
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"Overlap ({chunk_overlap}) must be less than "
                f"chunk size ({chunk_size})"
            )
    
    def chunk(
        self, 
        text: str,
        base_metadata: Optional[dict] = None
    ) -> list[DocumentChunk]:
        """Split text into overlapping chunks.
        
        Args:
            text: Text to split into chunks.
            base_metadata: Optional metadata to include in each chunk.
            
        Returns:
            List of DocumentChunk instances.
        """
        if not text or not text.strip():
            return []
        
        # Clean up text
        text = text.strip()
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            # Calculate end position
            end = start + self.chunk_size
            
            if end >= len(text):
                # Last chunk - take everything remaining
                chunk_text = text[start:].strip()
                if chunk_text:
                    chunks.append(DocumentChunk(
                        text=chunk_text,
                        chunk_index=chunk_index,
                        char_start=start,
                        char_end=len(text),
                        metadata=self._make_chunk_metadata(
                            base_metadata, chunk_index, len(text)
                        )
                    ))
                break
            
            # Try to find a good break point
            chunk_end = self._find_break_point(text, start, end)
            
            chunk_text = text[start:chunk_end].strip()
            if chunk_text:
                chunks.append(DocumentChunk(
                    text=chunk_text,
                    chunk_index=chunk_index,
                    char_start=start,
                    char_end=chunk_end,
                    metadata=self._make_chunk_metadata(
                        base_metadata, chunk_index, len(text)
                    )
                ))
                chunk_index += 1
            
            # Move start position with overlap
            start = max(start + 1, chunk_end - self.chunk_overlap)
        
        logger.debug(
            f"Split text ({len(text)} chars) into {len(chunks)} chunks"
        )
        return chunks
    
    def _find_break_point(self, text: str, start: int, end: int) -> int:
        """Find the best break point near the target end position.
        
        Tries to break at natural boundaries (paragraph, sentence, word)
        by searching for separators near the target end position.
        
        Args:
            text: Full text being chunked.
            start: Start position of current chunk.
            end: Target end position.
            
        Returns:
            Best break point position.
        """
        # Search window: look back up to 100 chars from target end
        search_start = max(start + self.chunk_size // 2, end - 100)
        
        for separator in self.separators:
            if not separator:
                continue
                
            # Find last occurrence of separator in search window
            pos = text.rfind(separator, search_start, end)
            if pos > start:
                # Include the separator in the chunk (for sentences)
                return pos + len(separator)
        
        # No good break point found, just break at target
        return end
    
    def _make_chunk_metadata(
        self,
        base_metadata: Optional[dict],
        chunk_index: int,
        total_chars: int
    ) -> dict:
        """Create metadata dict for a chunk.
        
        Args:
            base_metadata: Base metadata to extend.
            chunk_index: Index of this chunk.
            total_chars: Total characters in original text.
            
        Returns:
            Metadata dictionary.
        """
        metadata = dict(base_metadata) if base_metadata else {}
        metadata["chunk_index"] = chunk_index
        metadata["total_chars"] = total_chars
        return metadata
    
    def estimate_chunk_count(self, text: str) -> int:
        """Estimate the number of chunks for a text.
        
        Args:
            text: Text to estimate chunks for.
            
        Returns:
            Estimated number of chunks.
        """
        if not text:
            return 0
        
        text_len = len(text.strip())
        if text_len <= self.chunk_size:
            return 1
        
        # Effective step size considering overlap
        step = self.chunk_size - self.chunk_overlap
        return max(1, (text_len + step - 1) // step)


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    metadata: Optional[dict] = None
) -> list[DocumentChunk]:
    """Split text into overlapping chunks.
    
    Convenience function that creates a DocumentChunker and chunks text.
    
    Args:
        text: Text to split into chunks.
        chunk_size: Target size for each chunk in characters.
        chunk_overlap: Overlap between consecutive chunks.
        metadata: Optional metadata to include in each chunk.
        
    Returns:
        List of DocumentChunk instances.
    """
    chunker = DocumentChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return chunker.chunk(text, base_metadata=metadata)
