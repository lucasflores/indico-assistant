"""Celery tasks for indico_assistant plugin.

Feature: 006-vector-search-rag (sync tasks)
Feature: 011-realtime-attachment-indexing (indexing task)
"""

from indico_assistant.tasks.sync import (
    sync_event_documents,
    sync_all_documents,
    cleanup_orphaned_documents,
)
from indico_assistant.tasks.indexing import index_attachment_task

__all__ = [
    "sync_event_documents",
    "sync_all_documents", 
    "cleanup_orphaned_documents",
    "index_attachment_task",
]
