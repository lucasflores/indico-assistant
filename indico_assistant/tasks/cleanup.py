"""Retention: the assistant's own tables stop growing forever.

Feature: 004-chat-api (scheduled since the scalability audit, Phase 2)

Runs nightly. Deletes in batches (no single huge transaction); chat messages and their feedback go
with their session (ON DELETE CASCADE).
"""

import logging

from celery.schedules import crontab
from sqlalchemy import text

from indico.core.celery import celery
from indico.core.db import db

from indico_assistant.tasks.indexing import BULK_QUEUE


logger = logging.getLogger(__name__)

# (table, timestamp column, setting with the days kept; 0 = keep forever). The audit log holds questions,
# emails and IP addresses.
RETENTION = [
    ('plugin_assistant.chat_sessions', 'updated_at', 'retention_chat_days'),
    ('plugin_assistant.query_audit_log', 'created_at', 'retention_audit_days'),
    ('plugin_assistant.action_plans', 'created_at', 'retention_plan_days'),
    # counted from closing: a report that is not closed has no closed_at, so it never matches (spec 021 FR-020)
    ('plugin_assistant.issue_reports', 'closed_at', 'retention_report_days'),
    # spec 024: the trace text on its own schedule; a turn takes its steps and text with it (FR-013)
    ('plugin_assistant.turn_texts', 'created_at', 'retention_trace_text_days'),
    ('plugin_assistant.turns', 'started_at', 'retention_turn_days'),
]
BATCH_SIZE = 5000


def purge(table, column, days, batch_size=BATCH_SIZE):
    deleted = 0
    while True:
        count = db.session.execute(text(f'''
            DELETE FROM {table} WHERE id IN (
                SELECT id FROM {table} WHERE {column} < now() - make_interval(days => :days) LIMIT :batch)
        '''), {'days': days, 'batch': batch_size}).rowcount
        db.session.commit()
        deleted += count
        if count < batch_size:
            return deleted


# locked=False: idempotent and batched, and Indico's lock outlives a dead worker by 24 h
@celery.periodic_task(name='indico_assistant.retention', run_every=crontab(minute='11', hour='3'),
                      queue=BULK_QUEUE, plugin='assistant', locked=False)
def apply_retention(settings=None):
    from indico_assistant.plugin import AssistantPlugin

    settings = settings or AssistantPlugin.settings
    result = {table: purge(table, column, days)
              for table, column, setting in RETENTION if (days := settings.get(setting))}
    from indico_assistant.services.analytics import recorder
    if count := recorder.forget_orphan_texts():  # (after the chats went: their turns' text goes too, FR-011)
        result['turn_texts of deleted chats'] = count
    db.session.commit()
    logger.info('Retention: %s', result)
    return result
