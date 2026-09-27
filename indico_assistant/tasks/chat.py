"""Answering chat messages in Celery, so LLM calls never hold an Indico web worker."""

import logging

from celery.exceptions import SoftTimeLimitExceeded

from indico.core.celery import celery
from indico.core.db import db


logger = logging.getLogger(__name__)

CHAT_QUEUE = 'assistant'
# One answer is up to ~8 LLM calls; past this the user is told to retry instead of the worker waiting on.
SOFT_TIME_LIMIT = 120


@celery.task(name='indico_assistant_answer_chat', queue=CHAT_QUEUE, ignore_result=True,
             soft_time_limit=SOFT_TIME_LIMIT, time_limit=SOFT_TIME_LIMIT + 30)
def answer_chat(job_id, user_id, session_id, message):
    from indico_assistant.services.chat import get_chat_service, jobs
    from indico_assistant.services.chat.service import ChatServiceError, EventAccessDeniedError

    try:
        result = get_chat_service().answer(user_id, session_id, message)
    except SoftTimeLimitExceeded:
        db.session.rollback()
        jobs.finish(job_id, status='failed', error='TIMEOUT',
                    message='That took too long to answer. Try a narrower question.')
    except EventAccessDeniedError:
        db.session.rollback()
        jobs.finish(job_id, status='failed', error='ACCESS_DENIED', message='You no longer have access to this event')
    except ChatServiceError as exc:
        db.session.rollback()
        jobs.finish(job_id, status='failed', error='QUERY_PROCESSING_ERROR', message=str(exc))
    except Exception:
        db.session.rollback()
        logger.exception('Answering chat job %s failed', job_id)
        jobs.finish(job_id, status='failed', error='INTERNAL_ERROR', message='An unexpected error occurred')
    else:
        jobs.finish(job_id, status='done', message_id=str(result.message_id), response=result.response,
                    metadata=result.metadata)
