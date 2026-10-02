"""The recorder (spec 024): one turn per chat answer, with its steps and their text.

A turn lives in a context variable for the length of ``answer_chat``. It is written twice:
- when the worker starts it: a row stamping who and where, from the question and the user (FR-002), so a turn that
  fails before routing has them, and one the worker never finishes still counts (as "no end record");
- when the task ends, whatever the outcome: the outcome, the totals, the fields, the steps and their text.

Both writes go through ``db.session`` at the task's two clean points: the start, and after the answer was committed
or rolled back. The end write rolls back first, so nothing of the answer's rides along (FR-006, FR-023). A failing
write is logged and never reaches the answer. Outside a turn (tests, the CLI, carrying out a plan) every call does
nothing, so the services call it unconditionally.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import time
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text as sql

from indico.core.db import db

logger = logging.getLogger(__name__)

TEXT_LIMIT = 100_000  # characters per text; longer ones are cut and marked (spec, edge cases)

# what the services may set on a turn (the rest is the recorder's own)
FIELDS = frozenset({'answer_id', 'route', 'decided_by', 'jev_confidence', 'fallback', 'intent', 'corrections',
                    'row_count', 'truncated', 'sql_ms', 'plan_id', 'tool_calls', 'record'})

_current: contextvars.ContextVar[_Turn | None] = contextvars.ContextVar('assistant_analytics_turn', default=None)

# who and where, from the question's row and the user's (a NULL where either is gone)
_START = sql('''
    INSERT INTO plugin_assistant.turns (job_id, user_id, is_admin, session_id, message_id, event_id, category_id,
                                        queued_at, started_at, private)
    SELECT :job_id, :user_id, u.is_admin, :session_id, :message_id, ev.id, ev.category_id, m.created_at, now(), false
    FROM (SELECT 1) AS one
    LEFT JOIN users.users u ON u.id = :user_id
    LEFT JOIN plugin_assistant.chat_messages m ON m.id = :message_id
    LEFT JOIN events.events ev ON ev.id = CASE WHEN m.metadata_json->>'event_id' ~ '^[0-9]+$'
                                               THEN (m.metadata_json->>'event_id')::int END
    RETURNING id
''')


@dataclass
class Step:
    """One model call, query, Jev call or tool call; the caller fills in what it knows."""

    kind: str
    stage: str | None = None
    name: str | None = None
    seq: int = 0
    parent_seq: int | None = None
    offset_ms: int | None = None
    duration_ms: int | None = None
    ok: bool = True
    error_code: str | None = None
    requested_model: str | None = None
    served_model: str | None = None
    ibis_chosen: str | None = None
    ibis_dial: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: Decimal | None = None
    attempts: int | None = None
    row_count: int | None = None
    http: list[int] = field(default_factory=list)  # each HTTP attempt's status (factory.py's hook); not stored

    def row(self, turn_id):
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != 'http'} | {'turn_id': turn_id}


class _Turn:
    def __init__(self, turn_id, text_on):
        self.id = turn_id
        self.t0 = time.monotonic()
        self.text_on = text_on
        self.private = False
        self.steps: list[Step] = []
        self.stack: list[Step] = []
        self.texts: dict[tuple[int, str], tuple[str, bool]] = {}
        self.fields: dict[str, Any] = {}
        self.outcome: str | None = None
        self.error_code: str | None = None

    def ms(self):
        return int((time.monotonic() - self.t0) * 1000)


@contextlib.contextmanager
def turn(job_id, user_id, session_id, message_id):
    """Around the whole of ``answer_chat``: the start row on entry, everything else on exit."""
    current = None
    try:
        turn_id = db.session.execute(_START, {'job_id': job_id, 'user_id': user_id, 'session_id': str(session_id),
                                              'message_id': str(message_id) if message_id else None}).scalar()
        db.session.commit()
        current = _Turn(turn_id, _text_on())
    except Exception:
        db.session.rollback()
        logger.exception('Analytics: could not record the start of chat job %s', job_id)
    token = _current.set(current)
    try:
        yield current
    except BaseException:  # (the task catches its own exceptions; this is the last resort)
        if current is not None and current.outcome is None:
            current.outcome, current.error_code = 'failed', 'internal'
        raise
    finally:
        _current.reset(token)
        if current is not None:
            try:
                _write_end(current)
            except Exception:
                db.session.rollback()
                logger.exception('Analytics: could not record the end of chat job %s', job_id)


def _write_end(current):
    from indico_assistant.models import FeedbackEntry, Turn, TurnStep, TurnText

    db.session.rollback()  # the answer committed, or was rolled back: nothing of it may ride along
    steps = current.steps
    calls = [s for s in steps if s.kind in ('llm', 'jev')]
    values = {
        **current.fields,
        'outcome': current.outcome or 'answered',
        'error_code': current.error_code,
        'private': current.private,
        'finished_at': datetime.now(UTC),
        'llm_calls': len(calls),
        'prompt_tokens': _sum(s.prompt_tokens for s in steps),
        'completion_tokens': _sum(s.completion_tokens for s in steps),
        'cost_usd': _sum(s.cost_usd for s in steps),
        'unpriced_calls': sum(1 for s in calls if s.cost_usd is None),
    }
    if answer_id := values.get('answer_id'):  # a vote cast before this write (FR-007; the feedback hook missed it)
        values['rating'] = (select(db.case((FeedbackEntry.feedback_type == 'thumbs_up', 1), else_=-1))
                            .where(FeedbackEntry.message_id == answer_id,
                                   FeedbackEntry.feedback_type.in_(('thumbs_up', 'thumbs_down')))
                            .order_by(FeedbackEntry.created_at.desc()).limit(1).scalar_subquery())
    turns = Turn.__table__
    db.session.execute(turns.update().where(turns.c.id == current.id).values(**values))
    if steps:
        db.session.execute(TurnStep.__table__.insert(), [s.row(current.id) for s in steps])
    if current.texts and not current.private:
        db.session.execute(TurnText.__table__.insert(), [
            {'turn_id': current.id, 'seq': seq, 'kind': kind, 'text': value, 'cut': cut}
            for (seq, kind), (value, cut) in current.texts.items()])
    db.session.commit()


def _sum(values):
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def _text_on():
    from indico_assistant.default_settings import DEFAULT_SETTINGS
    try:
        from indico_assistant.plugin import AssistantPlugin
        return bool(AssistantPlugin.settings.get('analytics_trace_text'))
    except RuntimeError:  # (the plugin isn't loaded: tests, scripts)
        return DEFAULT_SETTINGS['analytics_trace_text']


@contextlib.contextmanager
def step(kind, stage=None, name=None):
    """One step of the current turn, timed; an exception marks it failed and goes on. Outside a turn: a no-op."""
    current = _current.get()
    item = Step(kind=kind, stage=stage, name=name)
    if current is None:
        yield item
        return
    item.seq = len(current.steps) + 1
    item.parent_seq = current.stack[-1].seq if current.stack else None
    item.offset_ms = current.ms()
    current.steps.append(item)
    current.stack.append(item)
    try:
        yield item
    except BaseException as exc:
        item.ok = False
        item.error_code = item.error_code or type(exc).__name__
        raise
    finally:
        current.stack.pop()
        item.duration_ms = current.ms() - item.offset_ms


def current_step():
    """The innermost open step of the current turn (for the HTTP hook), or None."""
    current = _current.get()
    return current.stack[-1] if current is not None and current.stack else None


def text(item, kind, value):
    """Keep a step's text (prompt, response, sql or rows), unless text is off or the turn is private."""
    current = _current.get()
    if current is None or current.private or not current.text_on or value is None or not item.seq:
        return
    value = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    current.texts[(item.seq, kind)] = (value[:TEXT_LIMIT], len(value) > TEXT_LIMIT)


def private():
    """This turn keeps no text, and what it collected so far goes (FR-009)."""
    if current := _current.get():
        current.private = True
        current.texts.clear()


def is_private():
    current = _current.get()
    return bool(current and current.private)


def update(**values):
    """Set turn fields; ``record`` is merged. An unknown field is logged and ignored: never an error in an answer."""
    current = _current.get()
    if current is None:
        return
    for key, value in values.items():
        if key not in FIELDS:
            logger.warning('Analytics: no turn field %r', key)
        elif key == 'record':
            current.fields['record'] = {**current.fields.get('record', {}), **value}
        else:
            current.fields[key] = value


def set_outcome(outcome, error_code=None):
    if current := _current.get():
        current.outcome, current.error_code = outcome, error_code


def outcome():
    current = _current.get()
    return current.outcome if current else None
