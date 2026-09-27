"""Chat job state: created pending for one user, finished with the worker's payload."""

from unittest.mock import patch

from indico_assistant.services.chat import jobs


class FakeCache(dict):
    def set(self, key, value, timeout=None):
        assert timeout == jobs.TTL
        self[key] = value


def test_lifecycle():
    with patch.object(jobs, '_cache', FakeCache()):
        job_id = jobs.create(7, 'session-uuid')
        assert jobs.get(job_id) == {'status': 'pending', 'user_id': 7, 'session_id': 'session-uuid'}
        jobs.finish(job_id, status='done', response='Hi')
        assert jobs.get(job_id) == {'status': 'done', 'user_id': 7, 'session_id': 'session-uuid', 'response': 'Hi'}
        assert jobs.create(7, 's') != job_id
