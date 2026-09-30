"""The user's own reports (spec 021, US2): list, view and delete through the API, and merged accounts."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

import indico_assistant.controllers.reports as reports_module
import indico_assistant.services.reports as service
from indico_assistant.controllers.reports import RHReportDelete, RHReportDetail, RHReportList
from indico_assistant.models import IssueReport


@pytest.fixture
def users(create_user):
    return {'lucas': create_user(20, first_name='Lucas', admin=True), 'makoto': create_user(21, first_name='Makoto')}


def filed(db, user, text='It broke.', copy=None, **fields):
    row = IssueReport(user_id=user.id, form_key=uuid4(), category='bug', text=text, copy=copy, **fields)
    db.session.add(row)
    db.session.flush()
    return row


def call(rh_class, user, monkeypatch, **view_args):
    request = MagicMock()
    request.view_args = view_args
    monkeypatch.setattr(reports_module, 'request', request)
    rh = rh_class.__new__(rh_class)
    rh._user = user
    response, status = rh._process()
    return status, response.get_json() if hasattr(response, 'get_json') else None


COPY = {'taken_at': '2026-10-01T10:00:00+00:00', 'reported_answer_id': 'a1', 'truncated': False, 'messages': [
    {'id': 'q1', 'role': 'user', 'content': 'When is the Sync?', 'created_at': '…', 'event_id': 351,
     'uploads': [{'filename': 'agenda.pdf'}]},
    {'id': 'a1', 'role': 'assistant', 'content': 'Tomorrow.', 'created_at': '…', 'sql_generated': 'SELECT 1',
     'pipeline_error': None, 'evidence': {'validation_rejection': 'x'}, 'problem': 'failed',
     'plan': {'summary': 'Move it', 'steps': ['Move "Sync"']}},
]}


def test_the_list_is_the_callers_own_newest_first(db, users, monkeypatch):
    older, newer = filed(db, users['lucas'], 'first ' + 'x' * 200), filed(db, users['lucas'], 'second')
    filed(db, users['makoto'], 'not yours')
    status, body = call(RHReportList, users['lucas'], monkeypatch)
    assert status == 200 and [r['report_id'] for r in body['reports']] == [newer.id, older.id]
    assert len(body['reports'][1]['text_start']) == 120
    assert set(body['reports'][0]) == {'report_id', 'category', 'text_start', 'status', 'note', 'created_at',
                                       'updated_at'}


def test_a_report_shows_the_messages_but_not_how_answers_were_made(db, users, monkeypatch):
    row = filed(db, users['lucas'], copy=COPY)
    status, body = call(RHReportDetail, users['lucas'], monkeypatch, report_id=row.id)
    question, answer = body['copy']['messages']
    assert status == 200 and body['text'] == 'It broke.'
    assert set(question) == {'id', 'role', 'content', 'created_at', 'uploads'}
    assert set(answer) == {'id', 'role', 'content', 'created_at', 'plan'}  # no query, error, problem or evidence


def test_someone_elses_report_is_refused_like_a_missing_one(db, users, monkeypatch):
    theirs = filed(db, users['makoto'])
    refused = call(RHReportDetail, users['lucas'], monkeypatch, report_id=theirs.id)
    missing = call(RHReportDetail, users['lucas'], monkeypatch, report_id=theirs.id + 1000)
    assert refused[0] == missing[0] == 404 and refused[1] == missing[1]


def test_the_reporter_deletes_their_report_and_only_they_can(db, users, monkeypatch):
    mine, theirs = filed(db, users['makoto']), filed(db, users['makoto'])
    assert call(RHReportDelete, users['makoto'], monkeypatch, report_id=mine.id)[0] == 204
    assert db.session.get(IssueReport, mine.id) is None
    assert call(RHReportDelete, users['lucas'], monkeypatch, report_id=theirs.id)[0] == 404  # an admin too
    assert db.session.get(IssueReport, theirs.id) is not None


def test_has_reports_follows_the_rows(db, users):
    assert not service.has_reports(users['makoto'])
    filed(db, users['makoto'])
    assert service.has_reports(users['makoto']) and not service.has_reports(users['lucas'])
