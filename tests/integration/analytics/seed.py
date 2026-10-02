"""A fixed seed for the stats queries (spec 024, T022), and the expected numbers computed from it in plain Python,
independently of the SQL in services/analytics/stats.py."""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from indico.core.db import db

from indico_assistant.models import Turn, TurnStep

BASE = datetime(2026, 8, 1, 9, tzinfo=UTC)
ROUTES = ('data', 'knowledge', 'chat', 'change', 'connector')
MODELS = ('openai/gpt-oss-120b', 'qwen/qwen3-32b')


@dataclass
class Spec:
    day: int
    user: int  # index into the seed's users; 0 is the admin
    route: str
    outcome: str | None
    rating: int | None
    wait_ms: int
    queue_ms: int
    event: int | None  # index into the seed's events
    corrections: int = 0
    row_count: int | None = None
    truncated: bool = False
    steps: list = field(default_factory=list)  # (kind, stage, model, cost, prompt, completion, ms, ok, code, http)
    session: int = 0


def specs():
    out = []
    for i in range(40):
        route = ROUTES[i % 5]
        model = MODELS[i % 2]
        cost = None if i % 7 == 0 else Decimal('0.0001') * (i + 1)
        steps = [('llm', 'QueryClassification', model, cost, 100 + i, 10, 200 + 10 * i, True, None,
                  [429] if i % 11 == 0 else None)]
        if route == 'data':
            steps.append(('sql', 'query', None, None, None, None, 50 + i, i % 10 != 0,
                          'timeout' if i % 10 == 0 else None, None))
        if route == 'connector':
            steps.append(('tool', 'github', None, None, None, None, 300, i % 3 != 0, None if i % 3 else '500', None))
        outcome = None if i == 39 else ('failed' if i % 9 == 0 else 'timeout' if i % 13 == 0 else 'answered')
        out.append(Spec(day=i % 20, user=i % 3, route=route, outcome=outcome, rating=(1, -1, None)[i % 3],
                        wait_ms=1000 + 100 * i, queue_ms=10 * i, event=i % 2 if i % 4 else None,
                        corrections=1 if route == 'data' and i % 2 else 0,
                        row_count=(0 if i % 3 == 0 else i) if route == 'data' else None,
                        truncated=route == 'data' and i % 4 == 0, steps=steps, session=i % 8))
    return out


def seed(users, events):
    """Insert the specs; returns (specs, turns). The last spec has no end record (started long ago, never finished)."""
    sessions = [uuid4() for _ in range(8)]
    rows = []
    for spec in specs():
        started = BASE + timedelta(days=spec.day, hours=spec.user)
        event = events[spec.event] if spec.event is not None else None
        calls = [s for s in spec.steps if s[0] in ('llm', 'jev')]
        costs = [s[3] for s in spec.steps if s[3] is not None]
        row = Turn(job_id=uuid4().hex, session_id=sessions[spec.session], message_id=uuid4(), answer_id=uuid4(),
                   user_id=users[spec.user].id, is_admin=spec.user == 0, route=spec.route, outcome=spec.outcome,
                   error_code='QUERY_PROCESSING_ERROR' if spec.outcome == 'failed' else None,
                   rating=spec.rating, queued_at=started - timedelta(milliseconds=spec.queue_ms), started_at=started,
                   finished_at=None if spec.outcome is None else
                   started - timedelta(milliseconds=spec.queue_ms) + timedelta(milliseconds=spec.wait_ms),
                   event_id=event.id if event else None, category_id=event.category_id if event else None,
                   llm_calls=len(calls), cost_usd=sum(costs) if costs else None,
                   unpriced_calls=sum(1 for s in calls if s[3] is None),
                   prompt_tokens=sum(s[4] for s in spec.steps if s[4] is not None) or None,
                   completion_tokens=sum(s[5] for s in spec.steps if s[5] is not None) or None,
                   intent='time_range' if spec.route == 'data' else None,
                   corrections=spec.corrections if spec.route == 'data' else None, row_count=spec.row_count,
                   truncated=spec.truncated if spec.route == 'data' else None)
        db.session.add(row)
        db.session.flush()
        for seq, (kind, stage, model, cost, prompt, completion, ms, ok, code, http) in enumerate(spec.steps, 1):
            db.session.add(TurnStep(turn_id=row.id, seq=seq, kind=kind, stage=stage, served_model=model,
                                    cost_usd=cost, prompt_tokens=prompt, completion_tokens=completion,
                                    duration_ms=ms, ok=ok, error_code=code, http_errors=http,
                                    name='my_pull_requests' if kind == 'tool' else None))
        rows.append(row)
    db.session.flush()
    return specs(), rows


def users_only(all_specs):
    """The default view: admins (user 0) left out."""
    return [s for s in all_specs if s.user != 0]


def pcont(values, fraction):
    """Postgres's percentile_cont."""
    values = sorted(values)
    if not values:
        return None
    k = (len(values) - 1) * fraction
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)
