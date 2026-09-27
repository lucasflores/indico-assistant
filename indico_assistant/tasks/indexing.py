"""Indexing attachments for document search: one entry point for uploads, edits and syncs.

Feature: 011-realtime-attachment-indexing (rewritten in the scalability audit, Phase 2)
"""

import logging

from sqlalchemy.exc import OperationalError

from indico.core.celery import celery
from indico.modules.attachments.models.attachments import Attachment, AttachmentType

from indico_assistant.models.document import ProcessingTier
from indico_assistant.services.document.validation import determine_processing_tier, is_supported_format


logger = logging.getLogger(__name__)

# Bulk work (indexing, syncs, cleanup) has its own queue so it never delays chat answers or Indico's
# own tasks; run workers with -Q ...,assistant_bulk (low concurrency is fine).
BULK_QUEUE = 'assistant_bulk'


def _vector_search_enabled():
    from indico_assistant.plugin import AssistantPlugin

    return AssistantPlugin.settings.get('vector_search_enabled')


def skip_reason(attachment):
    """Why this attachment must not be in the index (None: index it)."""
    if attachment is None:
        return 'not found'
    if attachment.is_deleted or attachment.folder.is_deleted:
        return 'deleted'
    if attachment.type != AttachmentType.file:
        return 'not a file'
    if attachment.folder.event_id is None:
        return 'not in an event'
    if not is_supported_format(attachment.file.filename):
        return 'unsupported format'
    if determine_processing_tier(attachment.file.size) == ProcessingTier.REJECTED:
        return 'too large'
    if not _vector_search_enabled():
        return 'vector search disabled'
    return None


def index_attachment(attachment, force=False, processor=None):
    """Bring the index in line with one attachment: (re)index it, or drop its chunks."""
    from indico_assistant.services.vector_search.store import VectorStore

    store = VectorStore()
    reason = skip_reason(attachment)
    if reason:
        # anything but a switched-off feature means the current version must not be searchable
        if attachment is not None and reason != 'vector search disabled':
            store.delete_attachment_chunks(attachment.id)
        return {'success': True, 'skipped': True, 'error': reason}
    if not store.is_available:
        return {'success': False, 'skipped': True, 'error': 'pgvector not available'}
    if not force and store.is_current(attachment.id, attachment.file_id):
        return {'success': True, 'skipped': True, 'error': 'current'}
    return (processor or _processor(store)).process_attachment(attachment, force=force)


def _processor(store):
    from indico_assistant.plugin import AssistantPlugin
    from indico_assistant.services.document import DocumentProcessor
    from indico_assistant.services.embedding import EmbeddingService

    # cheap to build: the embedding model itself is loaded once per process
    return DocumentProcessor(embedding_service=EmbeddingService(AssistantPlugin.instance), vector_store=store)


@celery.task(name='indico_assistant.index_attachment', queue=BULK_QUEUE, ignore_result=True,
             soft_time_limit=300, time_limit=360,
             autoretry_for=(OperationalError,), max_retries=3, retry_backoff=True)
def index_attachment_task(attachment_id, force=False):
    """Queued after the upload/edit commits, so the attachment is always visible here."""
    result = index_attachment(Attachment.get(attachment_id), force=force)
    if not result['success']:
        logger.warning('Indexing attachment %s failed: %s', attachment_id, result.get('error'))
    return result
