"""The turn list, one turn's trace, and the export (spec 024 US2, US5).

A trace shows a turn's question and answer, read from the chat, only while the turn still has its text and isn't
private, so admins read chat content for the same 30 days as the rest of the text (FR-010). A private turn (GitHub
data) shows neither, and never any text (FR-009).
"""

from __future__ import annotations

import csv
import io

from sqlalchemy import text as sql

from indico.core.db import db

from indico_assistant.services.analytics.stats import T, WAIT_MS, scope

PAGE = 50
EXPORT_MAX = 10_000

_LIST = f'''
    SELECT t.id, t.started_at, t.route, t.outcome, t.error_code, t.user_id,
           u.first_name || ' ' || u.last_name AS user_name, t.is_admin, t.event_id, t.cost_usd, t.llm_calls,
           t.prompt_tokens, t.completion_tokens, {WAIT_MS} AS wait_ms, t.rating, t.private, t.intent, t.decided_by,
           t.answer_id, t.session_id
    FROM {T} t LEFT JOIN users.users u ON u.id = t.user_id
    WHERE {{scope}} {{extra}}
    ORDER BY t.id DESC LIMIT :limit'''


def turn_list(q, outcome=None, before=None, limit=None):
    """Turns newest first, a page at a time (keyset: ``before`` is the last id of the previous page)."""
    limit = limit or PAGE
    extra = ''.join((' AND t.outcome = :outcome' if outcome else '', ' AND t.id < :before' if before else ''))
    rows = [dict(row._mapping) for row in db.session.execute(
        sql(_LIST.format(scope=scope(q), extra=extra)),
        {**q.bind(), 'outcome': outcome, 'before': before, 'limit': limit + 1})]
    return rows[:limit], (rows[limit - 1]['id'] if len(rows) > limit else None)


def by_answer(answer_id):
    """The turn that made this chat message."""
    from indico_assistant.models import Turn
    turn = Turn.query.filter_by(answer_id=answer_id).order_by(Turn.id.desc()).first()
    return turn.id if turn else None


def trace(turn_id):
    """Everything about one turn, in order; None when there is no such turn."""
    from indico_assistant.models import ActionPlan, ChatMessage, FeedbackEntry, IssueReport, Turn, TurnStep, TurnText

    turn = Turn.query.get(turn_id)
    if turn is None:
        return None
    steps = TurnStep.query.filter_by(turn_id=turn.id).order_by(TurnStep.seq).all()
    texts = {} if turn.private else {(t.seq, t.kind): t for t in TurnText.query.filter_by(turn_id=turn.id)}
    text_state = 'private' if turn.private else 'kept' if texts else 'none'  # (none: past retention, or off)
    question = answer = None
    if text_state == 'kept':  # the chat's own words, for the same days as the rest of the text (FR-010)
        question = db.session.get(ChatMessage, turn.message_id) if turn.message_id else None
        answer = db.session.get(ChatMessage, turn.answer_id) if turn.answer_id else None
    # (a private turn's comment may quote the GitHub data it was about: FR-009)
    comment = (FeedbackEntry.query.filter_by(message_id=turn.answer_id, feedback_type='comment')
               .order_by(FeedbackEntry.created_at.desc()).first()) if turn.answer_id and not turn.private else None
    plan = db.session.get(ActionPlan, turn.plan_id) if turn.plan_id else None
    reports = (IssueReport.query.filter(IssueReport.copy['reported_answer_id'].astext == str(turn.answer_id))
               .order_by(IssueReport.created_at).all()) if turn.answer_id else []
    return {
        'turn': _columns(turn),
        'text': text_state,
        'question': question.content if question else None,
        'answer': answer.content if answer else None,
        'comment': comment.value if comment else None,
        'steps': [{**_columns(step), 'texts': {kind: {'text': t.text, 'cut': t.cut}
                                               for (seq, kind), t in texts.items() if seq == step.seq}}
                  for step in steps],
        'plan': {'id': str(plan.id), 'status': plan.effective_status, 'summary': plan.summary,
                 'steps': [s.get('description', s.get('action')) for s in plan.steps],
                 'created_at': plan.created_at, 'confirmed_at': plan.confirmed_at,
                 'finished_at': plan.finished_at} if plan else None,
        'reports': [{'id': r.id, 'category': r.category, 'status': r.status, 'created_at': r.created_at}
                    for r in reports],
    }


def export(q, with_text=False):
    """The turns of the range and filters, newest first (at most 10,000), with their question and answer when asked
    and still kept; a private turn never has them (FR-009)."""
    rows, _ = turn_list(q, limit=EXPORT_MAX)
    if with_text:
        from indico_assistant.models import ChatMessage, TurnText
        kept = {turn_id for (turn_id,) in db.session.query(TurnText.turn_id).filter(
            TurnText.turn_id.in_([r['id'] for r in rows if not r['private']])).distinct()}
        ids = [i for r in rows if r['id'] in kept for i in (r.get('answer_id'),) if i]
        messages = {m.id: m for m in ChatMessage.query.filter(ChatMessage.id.in_(ids))} if ids else {}
        questions = _questions(rows, kept)
        for row in rows:
            row['question'] = questions.get(row['id'])
            answer = messages.get(row.get('answer_id'))
            row['answer'] = answer.content if answer and row['id'] in kept else None
    return rows


def _questions(rows, kept):
    from indico_assistant.models import ChatMessage, Turn
    pairs = dict(db.session.query(Turn.id, Turn.message_id).filter(Turn.id.in_(list(kept)))) if kept else {}
    found = {m.id: m.content for m in ChatMessage.query.filter(ChatMessage.id.in_(list(pairs.values())))} \
        if pairs else {}
    return {turn_id: found.get(message_id) for turn_id, message_id in pairs.items()}


def as_csv(rows):
    out = io.StringIO()
    fields = [k for k in (rows[0] if rows else {'id': None}) if k not in ('answer_id', 'session_id')]
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows({k: _cell(v) for k, v in row.items()} for row in rows)
    return out.getvalue()


def _cell(value):
    """A text a spreadsheet would run as a formula (a user's question can start with =), quoted so it stays text."""
    return f"'{value}" if isinstance(value, str) and value[:1] in ('=', '+', '-', '@', '\t', '\r') else value


def _columns(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
