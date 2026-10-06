"""Reading attachments into documents: one entry point for uploads, edits and syncs (spec 025, story 2).

Feature: 011-realtime-attachment-indexing (rewritten for spec 025: status rows, pages and sections)
"""

import logging

from celery.exceptions import SoftTimeLimitExceeded
from indico.core.celery import celery
from indico.core.db import db
from indico.modules.attachments.models.attachments import Attachment, AttachmentType
from sqlalchemy.exc import OperationalError

from indico_assistant.models.document import DocumentStatus, ProcessingTier
from indico_assistant.services.document import store
from indico_assistant.services.document.chunker import chunk_pages, indexed_text
from indico_assistant.services.document.extractor import UnsupportedFileTypeError, extract
from indico_assistant.services.document.structure import numbered_headings, outline
from indico_assistant.services.document.validation import determine_processing_tier, is_supported_format

logger = logging.getLogger(__name__)

# Bulk work (indexing, syncs, cleanup) has its own queue so it never delays chat answers or Indico's
# own tasks; run workers with -Q ...,assistant_bulk (low concurrency is fine).
BULK_QUEUE = "assistant_bulk"


def _vector_search_enabled():
    from indico_assistant.plugin import AssistantPlugin

    return AssistantPlugin.settings.get("vector_search_enabled")


def skip_reason(attachment):
    """Why this attachment has no document (None: read it)."""
    if attachment is None:
        return "not found"
    if attachment.is_deleted or attachment.folder.is_deleted:
        return "deleted"
    if attachment.type != AttachmentType.file:
        return "not a file"
    if attachment.folder.event_id is None:
        return "not in an event"
    if not _vector_search_enabled():
        return "disabled"
    return None


def unreadable_reason(attachment):
    """Why the plugin can't read this file (None: it can)."""
    if not is_supported_format(attachment.file.filename):
        return "unsupported format"
    if determine_processing_tier(attachment.file.size) == ProcessingTier.REJECTED:
        return "too large"
    return None


def _embedder():
    from indico_assistant.plugin import AssistantPlugin
    from indico_assistant.services.embedding import EmbeddingService

    return EmbeddingService(AssistantPlugin.instance)  # cheap: the model is loaded once per process


def index_attachment(attachment, force=False, embedder=None):
    """Bring the attachment's document in line with its current file: read it, or drop it."""
    reason = skip_reason(attachment)
    if reason:
        if reason not in ("not found", "disabled"):
            store.delete([attachment.id])
            db.session.commit()
        return {"status": None, "skipped": reason}
    doc = store.queue(attachment)
    db.session.commit()
    if not force and store.is_current(attachment):
        return {"status": doc.status, "skipped": "current"}
    attachment_id, file_id = attachment.id, attachment.file_id  # (this version: a newer one has its own task)
    if reason := unreadable_reason(attachment):
        store.mark(attachment_id, file_id, DocumentStatus.UNSUPPORTED, reason)
        return {"status": DocumentStatus.UNSUPPORTED.value}
    store.mark(attachment_id, file_id, DocumentStatus.READING)
    try:
        return _read(attachment, file_id, embedder)
    except SoftTimeLimitExceeded:
        db.session.rollback()
        store.mark(attachment_id, file_id, DocumentStatus.FAILED, "Time limit reached")
        raise
    except UnsupportedFileTypeError as exc:
        db.session.rollback()
        store.mark(attachment_id, file_id, DocumentStatus.UNSUPPORTED, str(exc))
        return {"status": DocumentStatus.UNSUPPORTED.value}
    except Exception as exc:  # the file, the embedder or the database: the row says so, nothing else fails
        db.session.rollback()
        logger.exception("Reading attachment %s failed", attachment_id)
        store.mark(attachment_id, file_id, DocumentStatus.FAILED, f"{type(exc).__name__}: {exc}"[:500])
        return {"status": DocumentStatus.FAILED.value}


def _read(attachment, file_id, embedder):
    filename = attachment.file.filename
    with attachment.file.get_local_path() as path:
        extracted = extract(path, filename)
    pages = extracted.pages
    if not any(p.strip() for p in pages):
        store.mark(attachment.id, file_id, DocumentStatus.NO_TEXT)
        return {"status": DocumentStatus.NO_TEXT.value}
    sections = outline(extracted.headings or numbered_headings(pages), len(pages))
    chunks = chunk_pages(pages, sections)
    title = attachment.title or filename
    indexed = [indexed_text(title, c.section, c.text) for c in chunks]
    embeddings = None
    if store.check_pgvector_available():
        try:
            embeddings = (embedder or _embedder()).embed_batch(indexed)
        except Exception:  # (vector search off, a model that won't load): the document is still found by keyword
            logger.exception("Embedding attachment %s failed: keyword search only", attachment.id)
    written = store.write(attachment.id, file_id, len(pages), sections, chunks, indexed, embeddings)
    return {"status": DocumentStatus.READY.value, "chunks": written}


@celery.task(
    name="indico_assistant.index_attachment",
    queue=BULK_QUEUE,
    ignore_result=True,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(OperationalError,),
    max_retries=3,
    retry_backoff=True,
)
def index_attachment_task(attachment_id, force=False):
    """Queued after the upload/edit commits, so the attachment is always visible here."""
    result = index_attachment(Attachment.get(attachment_id), force=force)
    if result.get("status") == DocumentStatus.FAILED.value:
        logger.warning("Reading attachment %s failed", attachment_id)
    return result
