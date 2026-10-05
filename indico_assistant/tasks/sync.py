"""Document sync: bring the documents in line with attachments (feature 006, reworked for spec 025).

What changed is found in SQL, without reading any file: Indico stores each file version as its own immutable
row, and each document records the ``file_id`` it was read from. Progress is in the documents' status rows.
"""

from __future__ import annotations

import logging

from celery.exceptions import SoftTimeLimitExceeded
from celery.schedules import crontab
from indico.core.celery import celery
from indico.core.db import db
from indico.modules.attachments.models.attachments import Attachment
from sqlalchemy import text

from indico_assistant.tasks.indexing import BULK_QUEUE, index_attachment, index_attachment_task

logger = logging.getLogger(__name__)

QUEUE_CHUNK = 500  # attachment ids per SQL page when queueing a full sync

# Live file attachments in events; {stale} limits to those whose current file has not been read to the end.
_ATTACHMENTS_SQL = """
    SELECT a.id FROM attachments.attachments a
    JOIN attachments.folders f ON f.id = a.folder_id
    WHERE NOT a.is_deleted AND NOT f.is_deleted AND a.type = 1 AND f.event_id IS NOT NULL
      {event_filter} {stale} AND a.id > :after
    ORDER BY a.id LIMIT :limit
"""
_STALE_SQL = """AND NOT EXISTS (
        SELECT 1 FROM plugin_assistant.documents d
        WHERE d.attachment_id = a.id AND d.file_id = a.file_id AND d.status IN ('ready', 'no_text', 'unsupported'))"""


def _attachment_ids(event_id=None, stale_only=False, limit=QUEUE_CHUNK):
    """Keyset-paginated attachment ids: memory stays flat however many attachments there are."""
    sql = _ATTACHMENTS_SQL.format(
        event_filter="AND f.event_id = :event_id" if event_id else "", stale=_STALE_SQL if stale_only else ""
    )
    after = 0
    while True:
        ids = [row[0] for row in db.session.execute(text(sql), {"event_id": event_id, "after": after, "limit": limit})]
        yield from ids
        if len(ids) < limit:
            return
        after = ids[-1]


@celery.task(name="indico_assistant.sync_event_documents", queue=BULK_QUEUE, soft_time_limit=3600, time_limit=3700)
def sync_event_documents(event_id: int, force: bool = False) -> dict:
    """(Re)read one event's attachments; unchanged ones are skipped without reading them."""
    statuses: dict[str, int] = {}
    try:
        for attachment_id in list(_attachment_ids(event_id)):
            result = index_attachment(Attachment.get(attachment_id), force=force)
            key = result.get("skipped") or result.get("status") or "none"
            statuses[key] = statuses.get(key, 0) + 1
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.warning("Document sync for event %s hit its time limit; run it again to continue", event_id)
        return {"success": False, "event_id": event_id, "statuses": statuses, "error": "time limit"}
    logger.info("Document sync for event %s: %s", event_id, statuses)
    return {"success": True, "event_id": event_id, "statuses": statuses}


@celery.task(name="indico_assistant.sync_all_documents", queue=BULK_QUEUE, soft_time_limit=3600, time_limit=3700)
def sync_all_documents(force: bool = False) -> dict:
    """Queue reading for every attachment whose current file hasn't been read yet.

    Safe to run twice: each queued task re-checks and skips what is already current.
    """
    queued = 0
    for attachment_id in _attachment_ids(stale_only=not force):
        index_attachment_task.delay(attachment_id, force=force)
        queued += 1
    logger.info("Queued reading for %d attachments", queued)
    return {"success": True, "attachments_queued": queued}


# locked=False: idempotent and batched, and Indico's lock outlives a dead worker by 24 h
@celery.periodic_task(
    name="indico_assistant.cleanup_orphaned_documents",
    run_every=crontab(minute="23", hour="3"),
    queue=BULK_QUEUE,
    plugin="assistant",
    locked=False,
)
def cleanup_orphaned_documents(batch_size: int = 5000) -> dict:
    """Drop documents of attachments that were deleted or turned into links (Indico soft-deletes), and mark
    documents stuck in ``reading`` (a worker that died) as failed.

    Deletes happen as they occur through the attachment and folder signals; this catches anything missed
    (deletions while the plugin was off). Batched, so no single huge transaction.
    """
    deleted = 0
    while True:
        count = db.session.execute(
            text("""
            DELETE FROM plugin_assistant.documents WHERE attachment_id IN (
                SELECT d.attachment_id FROM plugin_assistant.documents d
                LEFT JOIN attachments.attachments a ON a.id = d.attachment_id
                LEFT JOIN attachments.folders f ON f.id = a.folder_id
                WHERE a.id IS NULL OR a.is_deleted OR f.is_deleted OR a.type <> 1
                LIMIT :batch)
        """),
            {"batch": batch_size},
        ).rowcount
        db.session.commit()
        deleted += count
        if count < batch_size:
            break
    stuck = db.session.execute(text("""
        UPDATE plugin_assistant.documents SET status = 'failed', error = 'The worker stopped while reading it'
        WHERE status = 'reading' AND updated_at < now() - interval '1 hour'
    """)).rowcount
    db.session.commit()
    logger.info("Removed %d orphaned documents, failed %d stuck ones", deleted, stuck)
    return {"success": True, "deleted": deleted, "stuck": stuck}
