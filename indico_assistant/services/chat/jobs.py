"""State of queued chat answers, shared by the web tier and Celery workers (Indico's Redis cache).

POST /chat saves the user's message and queues the answer; the worker stores the result here and the
client polls GET /chat/jobs/<job_id>. Nothing here is durable: the conversation itself lives in the
chat tables, this only says whether the answer is ready.
"""

from uuid import uuid4

from indico.core.cache import make_scoped_cache


TTL = 3600  # long enough for any answer to be fetched; the chat tables keep the history

_cache = make_scoped_cache('assistant-chat-jobs')


def create(user_id, session_id):
    job_id = uuid4().hex
    _cache.set(job_id, {'status': 'pending', 'user_id': user_id, 'session_id': str(session_id)}, timeout=TTL)
    return job_id


def get(job_id):
    return _cache.get(job_id)


def finish(job_id, **result):
    """Mark a job done (``status='done'``) or failed (``status='failed'``) with its payload."""
    job = get(job_id) or {}
    job.update(result)
    _cache.set(job_id, job, timeout=TTL)
