"""Embedding cache for avoiding recomputation.

Feature: 006-vector-search-rag
Task: T011

Provides content-hash based caching to avoid re-embedding unchanged content.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """Cache for document embeddings based on content hash.
    
    This cache uses content hashes to determine if a document chunk
    has already been embedded. If the content hash matches, we can
    skip embedding generation and reuse the existing embedding.
    
    The cache stores mappings from content hash to embedding existence,
    NOT the actual embeddings (those are stored in the database).
    
    Attributes:
        _processed_hashes: Set of content hashes that have been processed.
    
    Example:
        >>> cache = EmbeddingCache()
        >>> content_hash = cache.compute_hash("document text")
        >>> if cache.is_cached(content_hash):
        ...     # Skip embedding, already processed
        ...     pass
        >>> else:
        ...     # Generate embedding
        ...     embedding = service.embed_text("document text")
        ...     cache.mark_cached(content_hash)
    """
    
    def __init__(self) -> None:
        """Initialize the embedding cache."""
        self._processed_hashes: set[str] = set()
    
    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute SHA-256 hash of content.
        
        Args:
            content: Text content to hash.
            
        Returns:
            Hexadecimal hash string (64 characters).
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def is_cached(self, content_hash: str) -> bool:
        """Check if content hash has been processed.
        
        Args:
            content_hash: SHA-256 hash of content.
            
        Returns:
            True if hash has been marked as cached.
        """
        return content_hash in self._processed_hashes
    
    def mark_cached(self, content_hash: str) -> None:
        """Mark content hash as processed.
        
        Args:
            content_hash: SHA-256 hash of content.
        """
        self._processed_hashes.add(content_hash)
    
    def invalidate(self, content_hash: str) -> None:
        """Invalidate a cached hash.
        
        Args:
            content_hash: SHA-256 hash to invalidate.
        """
        self._processed_hashes.discard(content_hash)
    
    def clear(self) -> None:
        """Clear all cached hashes."""
        self._processed_hashes.clear()
    
    def load_from_database(self, hashes: list[str]) -> None:
        """Load existing hashes from database.
        
        Used to pre-populate cache with hashes of already-indexed documents.
        
        Args:
            hashes: List of content hashes already in database.
        """
        self._processed_hashes.update(hashes)
        logger.debug(f"Loaded {len(hashes)} hashes into cache")
    
    @property
    def size(self) -> int:
        """Get number of cached hashes."""
        return len(self._processed_hashes)


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content.
    
    Convenience function for use without instantiating cache.
    
    Args:
        content: Text content to hash.
        
    Returns:
        Hexadecimal hash string (64 characters).
    """
    return EmbeddingCache.compute_hash(content)
