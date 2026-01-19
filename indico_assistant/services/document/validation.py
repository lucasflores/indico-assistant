"""File validation helpers for real-time indexing.

Feature: 011-realtime-attachment-indexing
Tasks: T006, T007, T008
"""

import os
from typing import Any

from indico_assistant.models.document import ProcessingTier


# Supported document formats for indexing
SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt', '.md'}

# File size thresholds in bytes
SIZE_FAST_THRESHOLD = 10 * 1024 * 1024  # 10MB - guaranteed fast processing
SIZE_BEST_EFFORT_THRESHOLD = 50 * 1024 * 1024  # 50MB - best effort, no SLA


def is_supported_format(filename_or_attachment: Any) -> bool:
    """Check if file format is supported for indexing.
    
    Supported formats: PDF, DOCX, DOC, TXT, MD
    
    Args:
        filename_or_attachment: Either a filename string or an Indico Attachment 
                               object with file attribute.
        
    Returns:
        True if file extension is supported, False otherwise.
        
    Example:
        >>> is_supported_format("document.pdf")
        True
        >>> is_supported_format("image.jpg")
        False
        >>> attachment = Mock(file=Mock(filename="document.pdf"))
        >>> is_supported_format(attachment)
        True
        
    Contract:
        See contracts/signal_handler.yaml step 4_check_format
    """
    # Handle string filename
    if isinstance(filename_or_attachment, str):
        filename = filename_or_attachment
    # Handle attachment object
    elif hasattr(filename_or_attachment, 'file') and hasattr(filename_or_attachment.file, 'filename'):
        filename = filename_or_attachment.file.filename
    else:
        return False
    
    if not filename:
        return False
    
    # Extract extension (lowercase for case-insensitive comparison)
    _, ext = os.path.splitext(filename.lower())
    
    return ext in SUPPORTED_EXTENSIONS


def determine_processing_tier(file_size_bytes: int) -> ProcessingTier:
    """Determine processing tier based on file size.
    
    File size tiers:
    - FAST: <10MB - High priority queue, 30s SLA, guaranteed processing
    - BEST_EFFORT: 10-50MB - Low priority queue, no SLA, logged warning
    - REJECTED: >=50MB - Not queued, logged info message, no error to user
    
    Args:
        file_size_bytes: File size in bytes.
        
    Returns:
        ProcessingTier enum value (FAST, BEST_EFFORT, or REJECTED).
        
    Example:
        >>> determine_processing_tier(5 * 1024 * 1024)  # 5MB
        ProcessingTier.FAST
        >>> determine_processing_tier(30 * 1024 * 1024)  # 30MB
        ProcessingTier.BEST_EFFORT
        >>> determine_processing_tier(100 * 1024 * 1024)  # 100MB
        ProcessingTier.REJECTED
        
    Contract:
        See data-model.md ProcessingTier enum section.
    """
    if file_size_bytes >= SIZE_BEST_EFFORT_THRESHOLD:
        return ProcessingTier.REJECTED
    elif file_size_bytes >= SIZE_FAST_THRESHOLD:
        return ProcessingTier.BEST_EFFORT
    else:
        return ProcessingTier.FAST
