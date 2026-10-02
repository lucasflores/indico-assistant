"""The page stays fast on a large history (spec 024, T039, SC-003): 50,000 turns and 400,000 steps."""

import random
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from indico.core.db import db

from indico_assistant.models import Turn, TurnStep
from indico_assistant.services.analytics import stats, turns

TURNS, STEPS_PER_TURN = 50_000, 8
ROUTES = ('data', 'knowledge', 'chat', 'change', 'connector')


@pytest.mark.slow
def test_the_stats_and_a_trace_on_fifty_thousand_turns(monkeypatch):
    rng = random.Random(24)
    now = datetime.now(UTC)
    sessions = [uuid4() for _ in range(5_000)]
    db.session.execute(Turn.__table__.insert(), [
        {'job_id': uuid4().hex, 'session_id': rng.choice(sessions), 'message_id': uuid4(), 'answer_id': uuid4(),
         'user_id': rng.randrange(1, 500), 'is_admin': rng.random() < 0.05, 'route': rng.choice(ROUTES),
         'outcome': 'answered', 'rating': rng.choice((1, -1, None, None)), 'llm_calls': STEPS_PER_TURN,
         'cost_usd': Decimal(rng.randrange(1, 900)) / 100_000, 'queued_at': now - timedelta(minutes=i),
         'started_at': now - timedelta(minutes=i), 'finished_at': now - timedelta(minutes=i) + timedelta(seconds=5),
         'jev_confidence': rng.random(), 'decided_by': 'jev'}
        for i in range(TURNS)])
    ids = [i for (i,) in db.session.query(Turn.id)]
    for start in range(0, len(ids), 5_000):
        db.session.execute(TurnStep.__table__.insert(), [
            {'turn_id': turn_id, 'seq': seq, 'kind': 'llm' if seq < 6 else 'sql', 'stage': f'Stage{seq}',
             'served_model': rng.choice(('a/x', 'b/y')), 'duration_ms': rng.randrange(50, 4000),
             'prompt_tokens': 1000, 'completion_tokens': 100, 'cost_usd': Decimal('0.0001'), 'ok': True}
            for turn_id in ids[start:start + 5_000] for seq in range(1, STEPS_PER_TURN + 1)])
    db.session.execute(db.text('ANALYZE plugin_assistant.turns; ANALYZE plugin_assistant.turn_steps'))
    q = stats.Params(since=now - timedelta(days=90), until=now + timedelta(minutes=1), tz='UTC')
    monkeypatch.setattr(stats, '_cache', type('Cache', (), {'get': lambda self, key: self.__dict__.get(key),
                                                            'set': lambda self, key, value, timeout: self.__dict__
                                                            .__setitem__(key, value)})())

    began = time.monotonic()
    stats.collect(q)
    uncached = time.monotonic() - began
    began = time.monotonic()
    stats.collect(q)
    cached = time.monotonic() - began
    began = time.monotonic()
    turns.trace(ids[len(ids) // 2])
    trace = time.monotonic() - began
    print(f'\nSC-003: stats uncached {uncached:.2f} s, cached {cached * 1000:.1f} ms, trace {trace * 1000:.0f} ms')
    assert uncached < 2 and cached < 0.1 and trace < 0.3
