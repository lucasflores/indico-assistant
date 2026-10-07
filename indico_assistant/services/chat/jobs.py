"""State of queued chat answers, shared by the web tier and Celery workers (Indico's Redis cache).

POST /chat saves the user's message and queues the answer; the worker stores the result here and the
client polls GET /chat/jobs/<job_id>. Nothing here is durable: the conversation itself lives in the
chat tables, this only says whether the answer is ready.
"""

import time
from uuid import uuid4

from indico.core.cache import make_scoped_cache


TTL = 3600  # long enough for any answer to be fetched; the chat tables keep the history

_cache = make_scoped_cache('assistant-chat-jobs')


def create(user_id, session_id):
    job_id = uuid4().hex
    _cache.set(job_id, {'status': 'pending', 'user_id': user_id, 'session_id': str(session_id)}, timeout=TTL)
    return job_id


def start(job_id):
    """Called by the worker when it begins: from then on a job can be declared lost."""
    finish(job_id, started_at=time.time())


def get(job_id):
    job = _cache.get(job_id)
    if job and job['status'] == 'pending' and 'started_at' in job:
        from indico_assistant.tasks.chat import HARD_TIME_LIMIT

        # Killed at the hard time limit, or the worker died: Celery calls none of our code then, and an
        # early-acked task is not redelivered (redelivery would repeat the LLM calls anyway).
        if time.time() - job['started_at'] > HARD_TIME_LIMIT + 10:
            job.update(status='failed', error='TIMEOUT',
                       message='That took too long to answer. Try a narrower question.')
    return job


def finish(job_id, **result):
    """Mark a job done (``status='done'``) or failed (``status='failed'``) with its payload."""
    job = get(job_id) or {'status': 'pending'}  # (expired meanwhile: kept in shape, or the next read fails)
    job.update(result)
    _cache.set(job_id, job, timeout=TTL)
