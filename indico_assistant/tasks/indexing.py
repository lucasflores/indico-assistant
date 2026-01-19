"""Celery task for asynchronous document indexing.

This module implements the indexing task that processes attachments
for vector search. It handles extraction, chunking, embedding, and storage.

Feature: 011-realtime-attachment-indexing
Tasks: T019-T030
"""

import time
import logging
from io import BytesIO
from celery import shared_task
from sqlalchemy.exc import IntegrityError
from indico.modules.attachments.models.attachments import Attachment
from indico.core.db import db

from indico_assistant.services.document.hasher import compute_content_hash
from indico_assistant.services.document.validation import determine_processing_tier
from indico_assistant.services.vector_search.store import VectorStore
from indico_assistant.services.document import DocumentExtractor
from indico_assistant.services.document import DocumentChunker
from indico_assistant.services.embedding import EmbeddingService
from indico_assistant.models.document import ExtractedDocument, ProcessingTier
from indico_assistant.schemas.document import IndexingTaskResult

logger = logging.getLogger(__name__)


@shared_task(
    name='indico_assistant.index_attachment',
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True
)
def index_attachment_task(
    self,
    attachment_id: int,
    event_id: int,
    force: bool = False,
    priority: str = 'normal'
) -> dict:
    """Index an attachment for vector search.
    
    This task implements the 8-step indexing workflow:
    1. Fetch attachment from database
    2. Compute content hash
    3. Check for duplicate by hash (skip if found unless force=True)
    4. Extract text from file
    5. Chunk text into segments
    6. Generate embeddings for chunks
    7. Store embeddings in vector database
    8. Return indexing result
    
    Args:
        attachment_id: ID of the attachment to index
        event_id: ID of the event the attachment belongs to
        force: If True, skip duplicate check and re-index
        priority: Task priority ('high', 'normal', 'low')
    
    Returns:
        dict: IndexingTaskResult as dictionary containing:
            - success (bool): True if indexing succeeded
            - status (str): 'indexed', 'skipped', or 'failed'
            - chunks_created (int): Number of new chunks created
            - chunks_skipped (int): Number of chunks skipped (duplicate)
            - content_hash (str): SHA256 hash of document content
            - attachment_id (int): ID of the attachment
            - event_id (int): ID of the event
            - error (str|None): Error message if failed
            - processing_time_ms (int): Task execution time in milliseconds
            - retry_count (int): Number of retries attempted
    
    Raises:
        Exception: Any errors are logged and returned in result dict
    
    Tasks: T019-T030
    FR-004: Complete indexing within 30s for <10MB files
    FR-006: Skip re-indexing when content hash matches
    """
    start_time = time.time()
    retry_count = self.request.retries
    
    logger.info(
        "Starting indexing task for attachment_id=%d, event_id=%d (force=%s, priority=%s, retry=%d)",
        attachment_id,
        event_id,
        force,
        priority,
        retry_count
    )
    
    try:
        # Step 1: Fetch attachment from database (T020)
        attachment = Attachment.query.get(attachment_id)
        if not attachment:
            error_msg = f'Attachment {attachment_id} not found or deleted'
            logger.error(error_msg)
            return IndexingTaskResult(
                success=False,
                status='failed',
                chunks_created=0,
                chunks_skipped=0,
                content_hash='',
                attachment_id=attachment_id,
                event_id=event_id,
                error=error_msg,
                processing_time_ms=int((time.time() - start_time) * 1000),
                retry_count=retry_count
            ).__dict__
        
        logger.debug("Fetched attachment: %s (size=%d bytes)", attachment.file.filename, attachment.file.size)
        
        # Step 2: Compute content hash (T021)
        with attachment.file.open() as f:
            content_hash = compute_content_hash(f)
        
        logger.debug("Computed content hash: %s", content_hash)
        
        # Step 3: Check duplicate by hash (T022)
        vector_store = VectorStore()
        
        if not force:
            duplicate = vector_store.check_duplicate_by_hash(event_id, content_hash)
            if duplicate:
                logger.info(
                    "Skipping duplicate document (content_hash=%s, original_attachment_id=%d, chunks=%d)",
                    content_hash,
                    duplicate['attachment_id'],
                    duplicate['chunk_count']
                )
                return IndexingTaskResult(
                    success=True,
                    status='skipped',
                    chunks_created=0,
                    chunks_skipped=duplicate['chunk_count'],
                    content_hash=content_hash,
                    attachment_id=attachment_id,
                    event_id=event_id,
                    error=None,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    retry_count=retry_count
                ).__dict__
        
        # Step 4: Extract text from file (T023)
        with attachment.file.open() as f:
            extractor = DocumentExtractor()
            text = extractor.extract_text(f, attachment.file.filename)
        
        if not text or len(text.strip()) == 0:
            error_msg = 'No text could be extracted from document'
            logger.error("Text extraction failed for attachment_id=%d: %s", attachment_id, error_msg)
            return IndexingTaskResult(
                success=False,
                status='failed',
                chunks_created=0,
                chunks_skipped=0,
                content_hash=content_hash,
                attachment_id=attachment_id,
                event_id=event_id,
                error=error_msg,
                processing_time_ms=int((time.time() - start_time) * 1000),
                retry_count=retry_count
            ).__dict__
        
        logger.debug("Extracted %d characters of text", len(text))
        
        # Step 5: Chunk text into segments (T024)
        chunker = DocumentChunker()
        chunks = chunker.chunk_text(text)
        
        if not chunks:
            error_msg = 'Text chunking produced no results'
            logger.error("Text chunking failed for attachment_id=%d: %s", attachment_id, error_msg)
            return IndexingTaskResult(
                success=False,
                status='failed',
                chunks_created=0,
                chunks_skipped=0,
                content_hash=content_hash,
                attachment_id=attachment_id,
                event_id=event_id,
                error=error_msg,
                processing_time_ms=int((time.time() - start_time) * 1000),
                retry_count=retry_count
            ).__dict__
        
        logger.debug("Created %d text chunks", len(chunks))
        
        # Step 6: Generate embeddings (T025)
        embedding_service = EmbeddingService()
        embeddings = embedding_service.embed_texts(chunks)
        
        logger.debug("Generated %d embeddings", len(embeddings))
        
        # Step 7: Store embeddings in vector database (T026)
        try:
            chunk_count = vector_store.insert_chunks(
                event_id=event_id,
                attachment_id=attachment_id,
                chunks=chunks,
                embeddings=embeddings,
                content_hash=content_hash
            )
        except IntegrityError as e:
            # Handle race condition: another task may have indexed this document
            # This can happen if duplicate detection check passes but insertion conflicts
            logger.warning(
                "IntegrityError during chunk insertion for attachment_id=%d: %s (likely race condition)",
                attachment_id,
                str(e)
            )
            db.session.rollback()
            
            # Return as skipped since another task handled it
            return IndexingTaskResult(
                success=True,
                status='skipped',
                chunks_created=0,
                chunks_skipped=len(chunks),
                content_hash=content_hash,
                attachment_id=attachment_id,
                event_id=event_id,
                error='Race condition: document already indexed by concurrent task',
                processing_time_ms=int((time.time() - start_time) * 1000),
                retry_count=retry_count
            ).__dict__
        
        # Step 8: Return result (T027)
        duration = time.time() - start_time
        
        logger.info(
            "Successfully indexed attachment_id=%d: %d chunks created in %.2fs",
            attachment_id,
            chunk_count,
            duration
        )
        
        return IndexingTaskResult(
            success=True,
            status='indexed',
            chunks_created=chunk_count,
            chunks_skipped=0,
            content_hash=content_hash,
            attachment_id=attachment_id,
            event_id=event_id,
            error=None,
            processing_time_ms=int(duration * 1000),
            retry_count=retry_count
        ).__dict__
    
    except Exception as e:
        duration = time.time() - start_time
        
        # Log error and return failure result
        logger.error(
            "Indexing task failed for attachment_id=%d: %s (duration=%.2fs, retry=%d)",
            attachment_id,
            str(e),
            duration,
            retry_count,
            exc_info=True
        )
        
        return IndexingTaskResult(
            success=False,
            status='failed',
            chunks_created=0,
            chunks_skipped=0,
            content_hash='',
            attachment_id=attachment_id,
            event_id=event_id,
            error=str(e),
            processing_time_ms=int(duration * 1000),
            retry_count=retry_count
        ).__dict__
