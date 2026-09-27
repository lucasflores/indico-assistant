"""Document synchronization Celery tasks: bring the search index in line with attachments.

Feature: 006-vector-search-rag (reworked in the scalability audit, Phase 2)

What changed is found in SQL, without reading any file: Indico stores each file version as its own
immutable row, and indexed chunks record the ``file_id`` they came from.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from celery.exceptions import SoftTimeLimitExceeded
from celery.schedules import crontab
from sqlalchemy import text

from indico.core.celery import celery
from indico.core.db import db
from indico.modules.attachments.models.attachments import Attachment

from indico_assistant.models.document import DocumentSyncLog, SyncStatus
from indico_assistant.services.document.validation import SUPPORTED_EXTENSIONS
from indico_assistant.services.vector_search import check_pgvector_available
from indico_assistant.tasks.indexing import BULK_QUEUE, index_attachment, index_attachment_task


logger = logging.getLogger(__name__)

QUEUE_CHUNK = 500  # attachment ids per SQL page when queueing a full sync

# Live file attachments in events, with a supported extension; {stale} limits to changed ones.
_ATTACHMENTS_SQL = '''
    SELECT a.id FROM attachments.attachments a
    JOIN attachments.folders f ON f.id = a.folder_id
    JOIN attachments.files af ON af.id = a.file_id
    WHERE NOT a.is_deleted AND NOT f.is_deleted AND a.type = 1 AND f.event_id IS NOT NULL
      AND lower(substring(af.filename from '\\.[^.]*$')) = ANY(:extensions)
      {event_filter} {stale} AND a.id > :after
    ORDER BY a.id LIMIT :limit
'''
_STALE_SQL = '''AND NOT EXISTS (
        SELECT 1 FROM plugin_assistant.extracted_documents d
        WHERE d.attachment_id = a.id AND d.metadata_json->>'file_id' = a.file_id::text)'''


def _attachment_ids(event_id=None, stale_only=False, limit=QUEUE_CHUNK):
    """Keyset-paginated attachment ids: memory stays flat however many attachments there are."""
    sql = _ATTACHMENTS_SQL.format(event_filter='AND f.event_id = :event_id' if event_id else '',
                                  stale=_STALE_SQL if stale_only else '')
    after = 0
    while True:
        ids = [row[0] for row in db.session.execute(text(sql), {
            'extensions': sorted(SUPPORTED_EXTENSIONS), 'event_id': event_id, 'after': after, 'limit': limit,
        })]
        yield from ids
        if len(ids) < limit:
            return
        after = ids[-1]


@celery.task(name='indico_assistant.sync_event_documents', queue=BULK_QUEUE,
             soft_time_limit=3600, time_limit=3700)
def sync_event_documents(event_id: int, force: bool = False) -> dict:
    """(Re)index one event's attachments; unchanged ones are skipped without reading them."""
    if not check_pgvector_available():
        return {'success': False, 'error': 'pgvector not available', 'event_id': event_id}

    sync_log = DocumentSyncLog(event_id=event_id, status=SyncStatus.RUNNING, started_at=datetime.now(timezone.utc))
    db.session.add(sync_log)
    db.session.commit()
    log_id = sync_log.id

    processed = errors = 0
    error_messages = []
    try:
        for attachment_id in list(_attachment_ids(event_id)):
            try:
                result = index_attachment(Attachment.get(attachment_id), force=force)
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:
                db.session.rollback()
                logger.exception('Indexing attachment %s failed', attachment_id)
                result = {'success': False, 'error': str(exc)}
            if not result['success']:
                errors += 1
                error_messages.append(f'Attachment {attachment_id}: {result.get("error")}')
            elif not result.get('skipped'):
                processed += 1
        status = SyncStatus.COMPLETED if errors == 0 else SyncStatus.PARTIAL
    except SoftTimeLimitExceeded:
        db.session.rollback()
        status = SyncStatus.FAILED
        error_messages.insert(0, 'Time limit reached; run the sync again to continue')

    sync_log = DocumentSyncLog.query.get(log_id)
    sync_log.status = status
    sync_log.completed_at = datetime.now(timezone.utc)
    sync_log.documents_processed = processed
    sync_log.documents_failed = errors
    sync_log.error_message = '; '.join(error_messages[:5]) or None
    db.session.commit()
    logger.info('Document sync for event %s: %d indexed, %d errors', event_id, processed, errors)
    return {'success': status != SyncStatus.FAILED, 'event_id': event_id, 'processed': processed,
            'errors': errors, 'error_messages': error_messages}


@celery.task(name='indico_assistant.sync_all_documents', queue=BULK_QUEUE,
             soft_time_limit=3600, time_limit=3700)
def sync_all_documents(force: bool = False) -> dict:
    """Queue indexing for every attachment whose current file version is not indexed yet.

    Safe to run twice: each queued task re-checks and skips what is already current.
    """
    if not check_pgvector_available():
        return {'success': False, 'error': 'pgvector not available'}
    queued = 0
    for attachment_id in _attachment_ids(stale_only=not force):
        index_attachment_task.delay(attachment_id, force=force)
        queued += 1
    logger.info('Queued indexing for %d attachments', queued)
    return {'success': True, 'attachments_queued': queued}


# locked=False: idempotent and batched, and Indico's lock outlives a dead worker by 24 h
@celery.periodic_task(name='indico_assistant.cleanup_orphaned_documents', run_every=crontab(minute='23', hour='3'),
                      queue=BULK_QUEUE, plugin='assistant', locked=False)
def cleanup_orphaned_documents(batch_size: int = 5000) -> dict:
    """Drop chunks of attachments that were deleted or turned into links (Indico soft-deletes).

    Deletes happen as they occur through the attachment/folder signals; this catches anything missed
    (e.g. deletions while the plugin was off). Batched, so no single huge transaction.
    """
    deleted = 0
    while True:
        count = db.session.execute(text('''
            DELETE FROM plugin_assistant.extracted_documents WHERE id IN (
                SELECT d.id FROM plugin_assistant.extracted_documents d
                LEFT JOIN attachments.attachments a ON a.id = d.attachment_id
                LEFT JOIN attachments.folders f ON f.id = a.folder_id
                WHERE a.id IS NULL OR a.is_deleted OR f.is_deleted OR a.type <> 1
                LIMIT :batch)
        '''), {'batch': batch_size}).rowcount
        db.session.commit()
        deleted += count
        if count < batch_size:
            break
    # sync runs whose worker died stay "running" forever otherwise
    stale = DocumentSyncLog.query.filter(
        DocumentSyncLog.status == SyncStatus.RUNNING,
        DocumentSyncLog.started_at < datetime.now(timezone.utc) - timedelta(hours=6),
    ).update({'status': SyncStatus.FAILED, 'error_message': 'Worker stopped before finishing'},
             synchronize_session=False)
    db.session.commit()
    logger.info('Removed %d orphaned chunks, closed %d stale sync runs', deleted, stale)
    return {'success': True, 'deleted': deleted, 'stale_sync_runs': stale}
