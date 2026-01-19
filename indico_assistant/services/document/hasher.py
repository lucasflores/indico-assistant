"""Content hashing utilities for duplicate detection.

Feature: 011-realtime-attachment-indexing
Tasks: T004, T005
"""

import hashlib
from typing import BinaryIO


def compute_content_hash(file_obj: BinaryIO) -> str:
    """Compute SHA256 hash of file content using streaming.
    
    Uses 8KB chunks to avoid loading entire file into memory.
    Suitable for files up to 50MB.
    
    Args:
        file_obj: File-like object opened in binary mode.
                 Must support read() method.
        
    Returns:
        Lowercase hexadecimal SHA256 hash (64 characters).
        
    Example:
        >>> with open('document.pdf', 'rb') as f:
        ...     hash_value = compute_content_hash(f)
        >>> len(hash_value)
        64
        >>> all(c in '0123456789abcdef' for c in hash_value)
        True
        
    Performance:
        - <100ms for 10MB files
        - Uses 8KB buffer to minimize memory usage
        
    Contract:
        See contracts/hasher.yaml for performance requirements.
        
    Tasks: T004, T005
    FR-006: Compute hash for duplicate detection
    """
    hasher = hashlib.sha256()
    
    # Read file in 8KB chunks to minimize memory usage
    chunk_size = 8192  # 8KB
    
    while True:
        chunk = file_obj.read(chunk_size)
        if not chunk:
            break
        hasher.update(chunk)
    
    return hasher.hexdigest()
