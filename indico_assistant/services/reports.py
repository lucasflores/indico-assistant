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
from sqlalchemy import tuple_
from sqlalchemy.dialects.postgresql import insert

from indico_assistant.models import ActionPlan, ChatMessage, ChatSession, IssueReport
from indico_assistant.models.report import CATEGORIES, NOTE_MAX, STATUSES, TEXT_MAX
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


def _no_conversation() -> ReportError:
    """The same refusal for someone else's conversation and one that does not exist (FR-003a). A new one each time:
    one shared instance, raised again and again, kept every traceback it passed through (fresh review)."""
    return ReportError(404, 'NOT_FOUND', 'Conversation not found')


def _uuid(value: Any, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise _invalid(field, f'{field} must be a UUID') from None


def _text(value: Any) -> str:
    """Trimmed, with a form's CRLF line breaks as LF: a textarea's maxlength counts a line break once, and the
    limits must agree with it (fresh review)."""
    return value.replace('\r\n', '\n').strip() if isinstance(value, str) else ''


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
    text = _text(data.get('text'))
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
        raise _no_conversation()
    query = ChatMessage.query.filter_by(session_id=chat.id)
    if answer_id is not None:
        answer = query.filter_by(id=answer_id, role='assistant').first()
        if answer is None:
            raise _no_conversation()
        query = query.filter(tuple_(ChatMessage.created_at, ChatMessage.id) <= (answer.created_at, answer.id))
    # the newest 50, and one more to know whether earlier ones were left out (a long chat is never read whole)
    newest = query.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(COPY_MESSAGES + 1).all()
    window = newest[:COPY_MESSAGES][::-1]
    plan_ids = {(m.metadata_json or {}).get('plan_id') for m in window} - {None}
    plans = {str(p.id): p for p in ActionPlan.query.filter(ActionPlan.id.in_(plan_ids))} if plan_ids else {}
    return {
        'taken_at': datetime.now(UTC).isoformat(),
        'reported_answer_id': str(answer_id) if answer_id else None,
        'truncated': len(newest) > COPY_MESSAGES,
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


# --- triage (US3) ------------------------------------------------------------------------------------------

PAGE_SIZE = 50


def _filters(status: str | None, category: str | None) -> tuple[str | None, str | None]:
    if status and status not in STATUSES:
        raise _invalid('status', 'Unknown status')
    if category and category not in CATEGORIES:
        raise _invalid('category', 'Unknown category')
    return status or None, category or None


def admin_list(status: str | None = None, category: str | None = None,
               page: int = 1) -> tuple[list[IssueReport], int, int]:
    """One page of every report, newest first, with the page shown and the page count (FR-015)."""
    status, category = _filters(status, category)
    query = IssueReport.query
    if status:
        query = query.filter_by(status=status)
    if category:
        query = query.filter_by(category=category)
    pages = max(1, -(-query.count() // PAGE_SIZE))
    page = min(max(1, page), pages)
    rows = (query.order_by(IssueReport.created_at.desc(), IssueReport.id.desc())
            .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all())
    return rows, page, pages


def open_count() -> int:
    return IssueReport.query.filter_by(status='open').count()


def admin_update(admin, report_id: int, status: Any, note: Any, seen: Any) -> IssueReport:
    """Save the status and the note, as ``admin`` (FR-017). ``seen`` is the report's ``updated_at`` as the admin's
    page showed it ('' when never updated): a save from an out-of-date page is refused, never applied over the
    newer one (R11). The check and the write are one UPDATE, so two admins saving at once cannot both win."""
    report = db.session.get(IssueReport, report_id)
    if report is None:
        raise ReportError(404, 'NOT_FOUND', 'Report not found')
    # what a save leaves out (None) stays as it is: a PATCH of the status alone must not erase the note (fresh review)
    status = report.status if status is None else status
    if status not in STATUSES:
        raise _invalid('status', 'Unknown status')
    note = (report.note or '') if note is None else _text(note)
    if len(note) > NOTE_MAX:
        raise _invalid('note', f'The note is at most {NOTE_MAX} characters')
    if (seen or '') != (report.updated_at.isoformat() if report.updated_at else ''):
        raise ReportError(409, 'STALE', 'The report changed since you opened it', {'report': admin_detail(report)})
    now = datetime.now(UTC)
    closed_at = (report.closed_at if report.status == 'closed' else now) if status == 'closed' else None
    same_version = (IssueReport.updated_at.is_(None) if report.updated_at is None
                    else IssueReport.updated_at == report.updated_at)
    saved = IssueReport.query.filter(IssueReport.id == report.id, same_version).update(
        {'status': status, 'note': note or None, 'updated_by_id': admin.id, 'updated_at': now, 'closed_at': closed_at},
        synchronize_session=False)
    db.session.refresh(report)
    if not saved:  # the other admin's save landed between our read and our write
        raise ReportError(409, 'STALE', 'The report changed since you opened it', {'report': admin_detail(report)})
    return report


def people(rows: list[IssueReport]) -> dict:
    """The reporters and the admins who saved these reports, by id, in one query (not one per row)."""
    from indico.modules.users import User
    ids = {row.user_id for row in rows} | {row.updated_by_id for row in rows if row.updated_by_id}
    return {user.id: user for user in User.query.filter(User.id.in_(ids))} if ids else {}


def _person(user, with_email: bool = False) -> dict | None:
    if user is None:
        return None
    return {'id': user.id, 'name': user.full_name, **({'email': user.email} if with_email else {})}


def admin_summary(report: IssueReport, known: dict) -> dict:
    return {**summary(report), 'user': _person(known.get(report.user_id))}


def admin_detail(report: IssueReport) -> dict:
    """Everything, for the team: the reporter as Indico knows them, and the whole copy with its evidence."""
    known = people([report])
    return {**summary(report), 'text': report.text, 'user': _person(known.get(report.user_id), with_email=True),
            'updated_by': _person(known.get(report.updated_by_id)), 'closed_at': _when(report.closed_at),
            'copy': report.copy}
