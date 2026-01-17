"""Celery tasks for indico_assistant plugin.

Feature: 006-vector-search-rag (sync tasks)
"""

from indico_assistant.tasks.sync import (
    sync_event_documents,
    sync_all_documents,
    cleanup_orphaned_documents,
)

__all__ = [
    "sync_event_documents",
    "sync_all_documents", 
    "cleanup_orphaned_documents",
]
