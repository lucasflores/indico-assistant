"""Document indexing schemas for real-time attachment processing.

Feature: 011-realtime-attachment-indexing
Tasks: T010, T011
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class IndexingTaskInput:
    """Input parameters for index_attachment_task.
    
    Attributes:
        attachment_id: Primary key of attachment to index.
        event_id: Event ID for permission checking and scoping.
        force: Force re-index even if hash matches (default: False).
        priority: Celery task priority (lower = higher priority).
                 5 = normal (FAST tier), 9 = low (BEST_EFFORT tier).
    
    Contract:
        See contracts/indexing_task.yaml Input Schema section.
    """
    attachment_id: int
    event_id: int
    force: bool = False
    priority: int = 5


@dataclass
class IndexingTaskResult:
    """Return value from index_attachment_task.
    
    Attributes:
        success: Overall success/failure status.
        attachment_id: Attachment that was processed.
        event_id: Event context.
        chunks_created: Number of new chunks inserted.
        chunks_skipped: Number of duplicate chunks skipped.
        processing_time_ms: Total processing time in milliseconds.
        content_hash: SHA256 hash of document content (64 hex chars).
        status: Processing outcome ('indexed', 'skipped', 'failed', 'rejected').
        error: Error message if failed (None if success).
        file_size_bytes: File size for metrics (default: 0).
        retry_count: Number of retry attempts (default: 0).
    
    Status values:
        - 'indexed': New document successfully indexed
        - 'skipped': Duplicate detected, no action taken
        - 'failed': Indexing failed after retries
        - 'rejected': File rejected (size/format)
    
    Contract:
        See contracts/indexing_task.yaml Output Schema section.
    """
    success: bool
    attachment_id: int
    event_id: int
    chunks_created: int
    chunks_skipped: int
    processing_time_ms: int
    content_hash: str
    status: str  # 'indexed', 'skipped', 'failed', 'rejected'
    error: Optional[str] = None
    file_size_bytes: int = 0
    retry_count: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "attachment_id": self.attachment_id,
            "event_id": self.event_id,
            "chunks_created": self.chunks_created,
            "chunks_skipped": self.chunks_skipped,
            "processing_time_ms": self.processing_time_ms,
            "content_hash": self.content_hash,
            "status": self.status,
            "error": self.error,
            "file_size_bytes": self.file_size_bytes,
            "retry_count": self.retry_count
        }
