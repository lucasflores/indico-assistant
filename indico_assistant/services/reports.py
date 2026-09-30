"""Issue reports (spec 021): sending one, and the frozen copy of the conversation it carries.

Feature: 021-issue-reports

The JSON API (``controllers/reports.py``) and the profile and admin pages (``controllers/report_pages.py``) both
go through here, so the rules live in one place (constitution II).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from indico.core.db import db
from indico.core.plugins import url_for_plugin
from sqlalchemy.dialects.postgresql import insert

from indico_assistant.models import ActionPlan, ChatMessage, ChatSession, IssueReport
from indico_assistant.models.report import CATEGORIES, TEXT_MAX
from indico_assistant.services.chat.rate_limiter import get_rate_limiter

COPY_MESSAGES = 50
# what a copy keeps of an answer's metadata (R6): an allowlist, so job ids and later keys never leak into it
ANSWER_KEYS = ('data_sources', 'sql_generated', 'confidence', 'pipeline_success', 'pipeline_error', 'problem',
               'evidence')


class ReportError(Exception):
    """A refusal, as the API answers it."""

    def __init__(self, status: int, code: str, message: str, details: dict | None = None,
                 retry_after: int | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details, self.retry_after = (status, code, message, details,
                                                                                 retry_after)


def _invalid(field: str, message: str) -> ReportError:
    return ReportError(422, 'VALIDATION_ERROR', message, {'field': field})


# the same refusal for someone else's conversation and one that does not exist (FR-003a)
_NO_CONVERSATION = ReportError(404, 'NOT_FOUND', 'Conversation not found')


def _uuid(value: Any, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise _invalid(field, f'{field} must be a UUID') from None


def report_url(report_id: int) -> str:
    """The reporter's page for the report (the chat's "Report sent" links to it)."""
    return url_for_plugin('assistant.user_report', report_id=report_id, _external=True)


def _find(user_id: int, form_key: UUID) -> IssueReport | None:
    return IssueReport.query.filter_by(user_id=user_id, form_key=form_key).first()


def create_report(user, data: Any) -> tuple[IssueReport, bool]:
    """Store the report a form sent, once (R8). Returns it and whether it is new.

    Sending the same form again returns the first report and counts nothing: a double click is one report.
    """
    data = data if isinstance(data, dict) else {}
    if data.get('category') not in CATEGORIES:
        raise _invalid('category', 'Pick one of the three kinds of problem')
    text = data.get('text').strip() if isinstance(data.get('text'), str) else ''
    if not text or len(text) > TEXT_MAX:
        raise _invalid('text', f'Say what happened, in at most {TEXT_MAX} characters')
    form_key = _uuid(data.get('form_key'), 'form_key')
    attach = data.get('attach') is True
    session_id = _uuid(data.get('session_id'), 'session_id') if attach else None
    answer_id = _uuid(data['answer_id'], 'answer_id') if attach and data.get('answer_id') else None

    if existing := _find(user.id, form_key):
        return existing, False
    limiter = get_rate_limiter()
    if not limiter.allowed(user.id, 'report'):
        raise ReportError(429, 'RATE_LIMITED', 'Too many reports', retry_after=limiter.retry_after(user.id, 'report'))
    copy = build_copy(user, session_id, answer_id) if attach else None
    report_id = db.session.execute(
        insert(IssueReport.__table__)
        .values(user_id=user.id, form_key=form_key, category=data['category'], text=text, copy=copy)
        .on_conflict_do_nothing(index_elements=['user_id', 'form_key'])
        .returning(IssueReport.__table__.c.id)
    ).scalar()
    if report_id is None:  # a twin request (the second click) stored it between our look and our insert
        return _find(user.id, form_key), False
    # ponytail: allowed() then count() is two steps, so two different forms sent at the same instant at the
    # 20th report make 21; one atomic step would need a Redis script
    limiter.count(user.id, 'report')
    return db.session.get(IssueReport, report_id), True


def build_copy(user, session_id: UUID, answer_id: UUID | None) -> dict:
    """The conversation as it is now: up to 50 messages ending at the reported answer (or the latest message).

    Read from Indico's own store, so the chat cannot forge it; frozen, so the team reads what the user saw even
    after the conversation is continued, deleted or purged (R6, FR-019).
    """
    chat = db.session.get(ChatSession, session_id)
    if chat is None or chat.user_id != user.id:
        raise _NO_CONVERSATION
    messages = ChatMessage.query.filter_by(session_id=chat.id).order_by(ChatMessage.created_at,
                                                                         ChatMessage.id).all()
    end = len(messages)
    if answer_id is not None:
        end = next((i + 1 for i, m in enumerate(messages) if m.id == answer_id and m.role == 'assistant'), None)
        if end is None:
            raise _NO_CONVERSATION
    window = messages[max(0, end - COPY_MESSAGES):end]
    plan_ids = {(m.metadata_json or {}).get('plan_id') for m in window} - {None}
    plans = {str(p.id): p for p in ActionPlan.query.filter(ActionPlan.id.in_(plan_ids))} if plan_ids else {}
    return {
        'taken_at': datetime.now(UTC).isoformat(),
        'reported_answer_id': str(answer_id) if answer_id else None,
        'truncated': end > COPY_MESSAGES,
        'messages': [_copied(m, plans) for m in window],
    }


def _copied(message: ChatMessage, plans: dict[str, ActionPlan]) -> dict:
    metadata = message.metadata_json or {}
    item = {'id': str(message.id), 'role': message.role, 'content': message.content,
            'created_at': message.created_at.isoformat()}
    if 'event_id' in metadata:
        item['event_id'] = metadata['event_id']  # the page it was sent from (spec 020)
    if uploads := metadata.get('uploads'):
        item['uploads'] = [{'filename': upload.get('filename')} for upload in uploads]
    if message.role == 'assistant':
        item.update({key: metadata[key] for key in ANSWER_KEYS if key in metadata})
        if plan := plans.get(metadata.get('plan_id')):
            # as the chat showed it: the plan row is purged by retention_plan_days, the copy is not
            item['plan'] = {'summary': plan.summary,
                            'steps': [step.get('description', step['action']) for step in plan.steps]}
    return item


# --- the user's own reports (US2) --------------------------------------------------------------------------

# what the reporter sees of their copy: the messages as the chat showed them. How answers were made (the query,
# its errors, the evidence) is for the team only (FR-013)
USER_KEYS = ('id', 'role', 'content', 'created_at', 'uploads', 'plan')
TEXT_START = 120


def own_reports(user) -> list[IssueReport]:
    return (IssueReport.query.filter_by(user_id=user.id)
            .order_by(IssueReport.created_at.desc(), IssueReport.id.desc()).all())


def own_report(user, report_id: int) -> IssueReport | None:
    """The report if it is ``user``'s; None for someone else's and for a missing one alike (FR-014)."""
    report = db.session.get(IssueReport, report_id)
    return report if report is not None and report.user_id == user.id else None


def delete_own(user, report_id: int) -> bool:
    """The reporter deletes their report and its copy, whatever its status (FR-013a)."""
    report = own_report(user, report_id)
    if report is None:
        return False
    db.session.delete(report)
    db.session.flush()
    return True


def has_reports(user) -> bool:
    return db.session.query(IssueReport.query.filter_by(user_id=user.id).exists()).scalar()


def _when(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def summary(report: IssueReport) -> dict:
    return {'report_id': report.id, 'category': report.category, 'text_start': report.text[:TEXT_START],
            'status': report.status, 'note': report.note, 'created_at': _when(report.created_at),
            'updated_at': _when(report.updated_at)}


def user_view(copy: dict | None) -> dict | None:
    if copy is None:
        return None
    return {**copy, 'messages': [{k: m[k] for k in USER_KEYS if k in m} for m in copy.get('messages', [])]}


def user_detail(report: IssueReport) -> dict:
    return {**summary(report), 'text': report.text, 'copy': user_view(report.copy)}
