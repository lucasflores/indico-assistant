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


def test_started_job_past_the_hard_limit_is_reported_lost():
    from indico_assistant.tasks.chat import HARD_TIME_LIMIT

    with patch.object(jobs, '_cache', FakeCache()), patch.object(jobs.time, 'time') as now:
        now.return_value = 1000.0
        queued, running = jobs.create(7, 's'), jobs.create(7, 's')
        jobs.start(running)
        now.return_value = 1000.0 + HARD_TIME_LIMIT + 11
        assert jobs.get(queued)['status'] == 'pending'  # still waiting for a worker: not lost
        assert (jobs.get(running)['status'], jobs.get(running)['error']) == ('failed', 'TIMEOUT')


def test_a_job_that_expired_before_it_started_stays_readable():
    """(story 3's run, through a laptop's sleep) start() on an expired job left one without a status: KeyError."""
    with patch.object(jobs, '_cache', FakeCache()):
        jobs.start('gone')
        assert jobs.get('gone')['status'] == 'pending'
