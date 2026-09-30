"""Sending a report: POST /reports (spec 021, US1) and the API base it stands on."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from flask import session
from sqlalchemy import text
from werkzeug.exceptions import BadRequest, TooManyRequests

import indico_assistant.controllers.reports as reports_module
import indico_assistant.services.reports as service
from indico_assistant.controllers.reports import RHReportCreate, RHReportsAPI
from indico_assistant.models import ActionPlan, ChatMessage, ChatSession, IssueReport, QueryAuditLog
from indico_assistant.services.chat.session_manager import get_session_manager

# --- T004: CSRF applies to requests made with the Indico session, not to the chat panel's token (R10) ------

def check_csrf(app, method, user=None, header=None, stored=None):
    with app.test_request_context(method=method, headers={'X-CSRF-Token': header} if header else {}):
        if user is not None:
            session.set_session_user(user)
        if stored:
            session['_csrf_token'] = stored
        RHReportsAPI()._check_csrf()


def test_a_session_write_without_the_csrf_token_is_refused(app, db, create_user):
    with pytest.raises(BadRequest):
        check_csrf(app, 'POST', create_user(20))


def test_a_session_write_with_the_wrong_csrf_token_is_refused(app, db, create_user):
    with pytest.raises(BadRequest):
        check_csrf(app, 'POST', create_user(20), header='forged', stored='the-real-one')


def test_a_session_write_with_the_csrf_token_passes(app, db, create_user):
    check_csrf(app, 'DELETE', create_user(20), header='the-real-one', stored='the-real-one')


def test_a_token_call_without_a_session_needs_no_csrf_token(app, db):
    check_csrf(app, 'POST')  # the chat panel's server: X-Assistant-Auth and no Indico cookie


def test_a_read_never_needs_one(app, db, create_user):
    check_csrf(app, 'GET', create_user(20))


# --- T009, T010: POST /reports -----------------------------------------------------------------------------



class FakeLimiter:
    def __init__(self, room=True):
        self.room, self.counted = room, 0

    def allowed(self, user_id, kind):
        assert kind == 'report'
        return self.room

    def count(self, user_id, kind):
        assert kind == 'report'
        self.counted += 1

    def retry_after(self, user_id, kind):
        return 42


@pytest.fixture
def limiter(monkeypatch):
    fake = FakeLimiter()
    monkeypatch.setattr(service, 'get_rate_limiter', lambda: fake)
    monkeypatch.setattr(service, 'report_url', lambda report_id: f'https://indico.test/user/assistant-reports/{report_id}/')
    return fake


@pytest.fixture
def users(create_user):
    return {'lucas': create_user(20, first_name='Lucas'), 'makoto': create_user(21, first_name='Makoto')}


def send(user, monkeypatch, **body):
    request = MagicMock()
    request.get_json.return_value = body
    monkeypatch.setattr(reports_module, 'request', request)
    rh = RHReportCreate.__new__(RHReportCreate)
    rh._user = user
    response, status = rh._process()
    return status, response.get_json()


def form(**fields):
    return {'form_key': str(uuid4()), 'category': 'wrong_answer', 'text': 'The date is wrong.', 'attach': False,
            **fields}


def chat_of(db, user, *messages):
    """A session with ``messages`` as (role, content) or (role, content, metadata), one second apart."""
    chat = ChatSession(user_id=user.id)
    db.session.add(chat)
    db.session.flush()
    start = datetime.now(UTC) - timedelta(hours=1)
    rows = []
    for i, (role, content, *metadata) in enumerate(messages):
        rows.append(ChatMessage(session_id=chat.id, role=role, content=content,
                                metadata_json=metadata[0] if metadata else None,
                                created_at=start + timedelta(seconds=i)))
    db.session.add_all(rows)
    db.session.flush()
    return chat, rows


def long_chat(db, user, n=60):
    return chat_of(db, user, *[('user' if i % 2 else 'assistant', f'message {i}') for i in range(1, n + 1)])


def reports():
    return IssueReport.query.count()


# T009: sending, resending, limits, validation


def test_a_report_is_created_counted_once_and_linked(db, users, limiter, monkeypatch):
    status, body = send(users['lucas'], monkeypatch, **form())
    row = IssueReport.query.one()
    assert status == 201 and body == {'report_id': row.id, 'url': f'https://indico.test/user/assistant-reports/{row.id}/'}
    assert (row.user_id, row.category, row.text, row.status, row.copy) == (users['lucas'].id, 'wrong_answer',
                                                                           'The date is wrong.', 'open', None)
    assert limiter.counted == 1


def test_sending_the_same_form_again_returns_the_same_report_uncounted(db, users, limiter, monkeypatch):
    sent = form()
    first = send(users['lucas'], monkeypatch, **sent)
    limiter.room = False  # a resend is never limited
    again = send(users['lucas'], monkeypatch, **sent)
    assert first[0] == 201 and again == (200, first[1]) and reports() == 1 and limiter.counted == 1


def test_a_double_click_racing_past_the_lookup_gets_the_first_report(db, users, limiter, monkeypatch):
    sent = form()
    send(users['lucas'], monkeypatch, **sent)
    real_find, looks = service._find, []

    def find(*args):  # the second request's first look came before the first request's row was committed
        looks.append(args)
        return None if len(looks) == 1 else real_find(*args)

    monkeypatch.setattr(service, '_find', find)
    status, body = send(users['lucas'], monkeypatch, **sent)
    assert status == 200 and body['report_id'] == IssueReport.query.one().id and limiter.counted == 1
    assert len(looks) == 2  # the insert found the twin and looked again: the ON CONFLICT path ran


def test_a_new_report_past_the_limit_is_refused_and_not_stored(db, users, limiter, monkeypatch):
    limiter.room = False
    with pytest.raises(TooManyRequests) as refused:
        send(users['lucas'], monkeypatch, **form())
    assert refused.value.response.status_code == 429 and refused.value.response.headers['Retry-After'] == '42'
    assert reports() == 0


@pytest.mark.parametrize('bad', [
    {'category': 'rant'},
    {'text': '   '},
    {'text': 'x' * 5001},
    {'form_key': 'not-a-uuid'},
    {'attach': True},  # attaching needs the conversation
    {'attach': True, 'session_id': 'not-a-uuid'},
])
def test_a_bad_field_is_refused_and_nothing_stored(db, users, limiter, monkeypatch, bad):
    status, body = send(users['lucas'], monkeypatch, **form(**bad))
    assert status == 422 and body['error'] == 'VALIDATION_ERROR' and reports() == 0 and limiter.counted == 0


def test_unticked_stores_nothing_from_the_conversation(db, users, limiter, monkeypatch):
    chat, rows = chat_of(db, users['lucas'], ('user', 'When is the Sync?'), ('assistant', 'Tomorrow.'))
    status, _ = send(users['lucas'], monkeypatch,
                     **form(attach=False, session_id=str(chat.id), answer_id=str(rows[1].id)))
    assert status == 201 and IssueReport.query.one().copy is None
    assert db.session.execute(text('SELECT copy IS NULL FROM plugin_assistant.issue_reports')).scalar() is True


# T010: the copy


def test_another_users_conversation_is_refused_like_a_missing_one(db, users, limiter, monkeypatch):
    chat, rows = chat_of(db, users['makoto'], ('user', 'Q'), ('assistant', 'A'))
    theirs = send(users['lucas'], monkeypatch, **form(attach=True, session_id=str(chat.id)))
    missing = send(users['lucas'], monkeypatch, **form(attach=True, session_id=str(uuid4())))
    assert theirs[0] == missing[0] == 404 and theirs[1] == missing[1] and reports() == 0


def test_an_answer_must_be_an_answer_in_that_conversation(db, users, limiter, monkeypatch):
    chat, rows = chat_of(db, users['lucas'], ('user', 'Q'), ('assistant', 'A'))
    other, other_rows = chat_of(db, users['lucas'], ('user', 'Q2'), ('assistant', 'A2'))
    for answer in (other_rows[1], rows[0]):  # from another conversation; a user message
        status, _ = send(users['lucas'], monkeypatch, **form(attach=True, session_id=str(chat.id),
                                                             answer_id=str(answer.id)))
        assert status == 404
    assert reports() == 0


def copy_of(db, users, limiter, monkeypatch, chat, answer=None):
    status, body = send(users['lucas'], monkeypatch,
                        **form(attach=True, session_id=str(chat.id), answer_id=str(answer.id) if answer else None))
    assert status == 201
    return IssueReport.query.get(body['report_id']).copy


def test_the_copy_ends_at_the_reported_answer_and_holds_at_most_50(db, users, limiter, monkeypatch):
    chat, rows = long_chat(db, users['lucas'])
    at_40 = copy_of(db, users, limiter, monkeypatch, chat, rows[39])
    assert [m['content'] for m in at_40['messages']] == [f'message {i}' for i in range(1, 41)]
    assert at_40['truncated'] is False and at_40['reported_answer_id'] == str(rows[39].id)
    at_60 = copy_of(db, users, limiter, monkeypatch, chat, rows[59])
    assert [m['content'] for m in at_60['messages']] == [f'message {i}' for i in range(11, 61)]
    assert at_60['truncated'] is True


def test_without_an_answer_the_copy_ends_at_the_latest_message(db, users, limiter, monkeypatch):
    chat, rows = chat_of(db, users['lucas'], ('user', 'Q'), ('assistant', 'A'), ('user', 'still waiting'))
    copy = copy_of(db, users, limiter, monkeypatch, chat)
    assert [m['content'] for m in copy['messages']] == ['Q', 'A', 'still waiting'] and copy['reported_answer_id'] is None


def test_the_copy_keeps_only_the_listed_keys(db, users, limiter, monkeypatch):
    evidence = {'intent': 'event_lookup', 'intent_confidence': 0.9, 'row_count': 3, 'validation_rejection': None,
                'correction_attempts': 0, 'corrected': False, 'cached': False}
    chat, rows = chat_of(
        db, users['lucas'],
        ('user', 'When is the Sync?', {'event_id': 351, 'job_id': 'j1', 'weird': 1,
                                       'uploads': [{'uuid': 'u1', 'filename': 'agenda.pdf'}]}),
        ('assistant', 'Tomorrow.', {'answer_id': 'a1', 'sql_generated': 'SELECT 1', 'confidence': 0.8,
                                    'data_sources': [{'type': 'event', 'event_id': 351}], 'pipeline_success': True,
                                    'pipeline_error': None, 'problem': 'failed', 'evidence': evidence, 'weird': 2}),
        ('assistant', 'An old answer.', {'sql_generated': 'SELECT 2'}),
    )
    question, answer, old = copy_of(db, users, limiter, monkeypatch, chat, rows[2])['messages']
    assert set(question) == {'id', 'role', 'content', 'created_at', 'event_id', 'uploads'}
    assert question['event_id'] == 351 and question['uploads'] == [{'filename': 'agenda.pdf'}]
    assert set(answer) == {'id', 'role', 'content', 'created_at', 'sql_generated', 'confidence', 'data_sources',
                           'pipeline_success', 'pipeline_error', 'problem', 'evidence'}
    assert answer['evidence'] == evidence and answer['pipeline_error'] is None
    assert set(old) == {'id', 'role', 'content', 'created_at', 'sql_generated'}  # missing keys left out, not nulled


def test_a_plan_is_frozen_into_the_copy(db, users, limiter, monkeypatch):
    plan = ActionPlan(user_id=users['lucas'].id, summary='Create "Sync" on Friday', token_hash='x' * 64,
                      steps=[{'n': 1, 'action': 'create_event', 'description': 'Create "Sync"'},
                             {'n': 2, 'action': 'add_reminder'}])
    db.session.add(plan)
    db.session.flush()
    chat, rows = chat_of(db, users['lucas'], ('user', 'Make a Sync'), ('assistant', 'Here is the plan.',
                                                                        {'plan_id': str(plan.id)}))
    copy = copy_of(db, users, limiter, monkeypatch, chat, rows[1])
    frozen = deepcopy(copy)
    assert copy['messages'][1]['plan'] == {'summary': 'Create "Sync" on Friday',
                                           'steps': ['Create "Sync"', 'add_reminder']}
    db.session.delete(plan)
    db.session.flush()
    assert IssueReport.query.one().copy == frozen


def test_the_copy_outlives_the_conversation(db, users, limiter, monkeypatch):
    chat, rows = chat_of(db, users['lucas'], ('user', 'Q'), ('assistant', 'A'))
    frozen = json.dumps(copy_of(db, users, limiter, monkeypatch, chat, rows[1]), sort_keys=True)
    db.session.add(ChatMessage(session_id=chat.id, role='user', content='and another thing'))
    db.session.flush()
    assert json.dumps(IssueReport.query.one().copy, sort_keys=True) == frozen
    assert get_session_manager().delete_session(chat.id)
    db.session.expire_all()
    assert json.dumps(IssueReport.query.one().copy, sort_keys=True) == frozen


def test_nothing_from_the_query_log_reaches_the_copy(db, users, limiter, monkeypatch):
    chat, rows = chat_of(db, users['lucas'], ('user', 'Q'), ('assistant', 'A'))
    # (the query log has its own declarative base, so the test database lacks it; this test's rollback drops it)
    QueryAuditLog.__table__.create(db.session.connection(), checkfirst=True)
    db.session.add(QueryAuditLog(user_id=users['lucas'].id, user_email='lucas.private@example.com',
                                 session_id=str(chat.id), question='Q', ip_address='10.1.2.3', success=True))
    db.session.flush()
    dumped = json.dumps(copy_of(db, users, limiter, monkeypatch, chat, rows[1]))
    assert 'lucas.private@example.com' not in dumped and '10.1.2.3' not in dumped
