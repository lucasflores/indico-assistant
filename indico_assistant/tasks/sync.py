"""Document synchronization Celery tasks.

Feature: 006-vector-search-rag
Tasks: T043-T046, T050-T052, T051

Background tasks for extracting and indexing event documents.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from celery import shared_task
from sqlalchemy import and_

from indico.core.celery import celery
from indico.core.db import db
from indico.modules.attachments.models.attachments import Attachment
from indico.modules.events.models.events import Event

from indico_assistant.models.document import (
    DocumentSyncLog,
    ExtractedDocument,
    ExtractionStatus,
    SyncStatus,
)
from indico_assistant.services.vector_search import check_pgvector_available

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Rate limiting configuration (T051)
DEFAULT_RATE_LIMIT_DELAY = 0.5  # seconds between documents
DEFAULT_BATCH_SIZE = 10  # documents per batch
DEFAULT_BATCH_DELAY = 2.0  # seconds between batches


@celery.task(bind=True, max_retries=3, rate_limit='10/m')
def sync_event_documents(
    self, 
    event_id: int, 
    force: bool = False,
    rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY
) -> dict:
    """Synchronize documents for a single event.
    
    Extracts text and embeddings from all attachments in the event.
    Includes rate limiting to prevent resource exhaustion (T051).
    
    Args:
        event_id: Event ID to sync.
        force: Force re-extraction of all documents.
        rate_limit_delay: Delay between processing documents (seconds).
        
    Returns:
        Dict with sync results.
    """
    from indico_assistant.services.document import DocumentProcessor
    from indico_assistant.services.embedding import EmbeddingService
    from indico_assistant.services.vector_search.store import VectorStore
    
    logger.info(f"Starting document sync for event {event_id}")
    
    # Check pgvector availability
    if not check_pgvector_available():
        logger.warning(f"pgvector not available, skipping sync for event {event_id}")
        return {
            "success": False,
            "error": "pgvector not available",
            "event_id": event_id
        }
    
    # Get event
    event = Event.query.get(event_id)
    if not event:
        logger.error(f"Event {event_id} not found")
        return {
            "success": False,
            "error": f"Event {event_id} not found",
            "event_id": event_id
        }
    
    # Create sync log
    sync_log = DocumentSyncLog(
        event_id=event_id,
        status=SyncStatus.RUNNING,
        started_at=datetime.utcnow()
    )
    db.session.add(sync_log)
    db.session.commit()
    
    try:
        # Initialize services
        embedding_service = EmbeddingService()
        vector_store = VectorStore()
        document_processor = DocumentProcessor(
            embedding_service=embedding_service,
            vector_store=vector_store
        )
        
        # Get attachments
        attachments = _get_event_attachments(event)
        
        processed = 0
        errors = 0
        error_messages = []
        
        for attachment in attachments:
            try:
                # Check if already processed (unless force)
                if not force and _is_attachment_current(attachment):
                    logger.debug(f"Attachment {attachment.id} already current, skipping")
                    continue
                
                # Process attachment
                result = document_processor.process_attachment(
                    attachment=attachment,
                    event_id=event_id,
                    force=force
                )
                
                if result.get("success"):
                    processed += 1
                else:
                    errors += 1
                    error_messages.append(
                        f"Attachment {attachment.id}: {result.get('error')}"
                    )
                
                # Rate limiting delay between documents (T051)
                if rate_limit_delay > 0:
                    time.sleep(rate_limit_delay)
                    
            except Exception as e:
                logger.exception(f"Error processing attachment {attachment.id}")
                errors += 1
                error_messages.append(f"Attachment {attachment.id}: {str(e)}")
        
        # Update sync log
        sync_log.status = SyncStatus.COMPLETED if errors == 0 else SyncStatus.PARTIAL
        sync_log.completed_at = datetime.utcnow()
        sync_log.documents_processed = processed
        sync_log.documents_failed = errors
        if error_messages:
            sync_log.error_message = "; ".join(error_messages[:5])  # Limit errors
        
        db.session.commit()
        
        logger.info(
            f"Document sync completed for event {event_id}: "
            f"{processed} processed, {errors} errors"
        )
        
        return {
            "success": True,
            "event_id": event_id,
            "processed": processed,
            "errors": errors,
            "error_messages": error_messages
        }
        
    except Exception as e:
        logger.exception(f"Document sync failed for event {event_id}")
        
        sync_log.status = SyncStatus.FAILED
        sync_log.completed_at = datetime.utcnow()
        sync_log.error_message = str(e)
        db.session.commit()
        
        # Retry on failure
        try:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            return {
                "success": False,
                "event_id": event_id,
                "error": str(e)
            }


@celery.task(bind=True, rate_limit='5/m')
def sync_all_documents(
    self, 
    force: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    batch_delay: float = DEFAULT_BATCH_DELAY
) -> dict:
    """Synchronize documents for all events with attachments.
    
    Queues individual sync tasks for each event with rate limiting (T051).
    
    Args:
        force: Force re-extraction of all documents.
        batch_size: Number of events to queue per batch.
        batch_delay: Delay between batches (seconds).
        
    Returns:
        Dict with queued task info.
    """
    logger.info("Starting full document sync")
    
    # Check pgvector availability
    if not check_pgvector_available():
        logger.warning("pgvector not available, skipping full sync")
        return {
            "success": False,
            "error": "pgvector not available"
        }
    
    # Get all events with attachments
    # Using subquery to find events with at least one attachment
    events_with_attachments = db.session.query(Event.id).join(
        Attachment, Attachment.event_id == Event.id
    ).distinct().all()
    
    event_ids = [e.id for e in events_with_attachments]
    
    logger.info(f"Queueing sync for {len(event_ids)} events (batch_size={batch_size})")
    
    # Queue sync tasks in batches with rate limiting (T051)
    queued = 0
    for i, event_id in enumerate(event_ids):
        sync_event_documents.delay(event_id=event_id, force=force)
        queued += 1
        
        # Add delay between batches to prevent overwhelming the system
        if batch_size > 0 and (i + 1) % batch_size == 0:
            logger.debug(f"Batch {(i + 1) // batch_size} complete, waiting {batch_delay}s")
            time.sleep(batch_delay)
    
    return {
        "success": True,
        "events_queued": queued
    }


@celery.task(bind=True)
def cleanup_orphaned_documents(self) -> dict:
    """Clean up documents for deleted events/attachments.
    
    Removes extracted documents where the source attachment
    no longer exists.
    
    Returns:
        Dict with cleanup results.
    """
    logger.info("Starting orphaned document cleanup")
    
    try:
        # Find orphaned documents (attachment no longer exists)
        orphaned = db.session.query(ExtractedDocument).outerjoin(
            Attachment, ExtractedDocument.attachment_id == Attachment.id
        ).filter(Attachment.id.is_(None)).all()
        
        deleted = 0
        for doc in orphaned:
            db.session.delete(doc)
            deleted += 1
        
        db.session.commit()
        
        logger.info(f"Cleaned up {deleted} orphaned documents")
        
        return {
            "success": True,
            "deleted": deleted
        }
        
    except Exception as e:
        logger.exception("Orphaned document cleanup failed")
        return {
            "success": False,
            "error": str(e)
        }


def _get_event_attachments(event: Event) -> list[Attachment]:
    """Get all attachments for an event.
    
    Includes attachments from contributions and subcontributions.
    
    Args:
        event: The Event object.
        
    Returns:
        List of Attachment objects.
    """
    # Supported file types for text extraction
    supported_types = {".pdf", ".docx", ".txt", ".md", ".markdown"}
    
    attachments = []
    
    # Event-level attachments
    for folder in event.attachment_folders:
        for attachment in folder.attachments:
            if attachment.file and any(
                attachment.file.filename.lower().endswith(ext) 
                for ext in supported_types
            ):
                attachments.append(attachment)
    
    # Contribution attachments
    for contribution in event.contributions:
        for folder in contribution.attachment_folders:
            for attachment in folder.attachments:
                if attachment.file and any(
                    attachment.file.filename.lower().endswith(ext)
                    for ext in supported_types
                ):
                    attachments.append(attachment)
        
        # Subcontribution attachments
        for subcontrib in contribution.subcontributions:
            for folder in subcontrib.attachment_folders:
                for attachment in folder.attachments:
                    if attachment.file and any(
                        attachment.file.filename.lower().endswith(ext)
                        for ext in supported_types
                    ):
                        attachments.append(attachment)
    
    return attachments


def _is_attachment_current(attachment: Attachment) -> bool:
    """Check if an attachment has already been processed with current content.
    
    Args:
        attachment: The Attachment to check.
        
    Returns:
        True if the attachment is already indexed with current hash.
    """
    import hashlib
    
    if not attachment.file:
        return True  # No file, nothing to process
    
    # Calculate content hash
    try:
        content_hash = hashlib.md5(
            attachment.file.open().read()
        ).hexdigest()
    except Exception:
        return False  # Can't read, assume not current
    
    # Check if we have this version
    existing = ExtractedDocument.query.filter(
        and_(
            ExtractedDocument.attachment_id == attachment.id,
            ExtractedDocument.content_hash == content_hash,
            ExtractedDocument.extraction_status == ExtractionStatus.COMPLETED
        )
    ).first()
    
    return existing is not None
