"""Triage (spec 021, US3): the admin endpoints. Admins list, filter, open and update every report; a save
made from an out-of-date view is refused, never applied over a newer one (FR-017, R11)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from flask import session
from werkzeug.exceptions import Forbidden

import indico_assistant.controllers.reports as reports_module
from indico_assistant.controllers.reports import RHAdminReportDetail, RHAdminReportList, RHAdminReportUpdate
from indico_assistant.models import IssueReport


@pytest.fixture
def users(create_user):
    return {'lucas': create_user(20, first_name='Lucas', admin=True), 'makoto': create_user(21, first_name='Makoto')}


def filed(db, user, category='bug', status='open', age_minutes=0, **fields):
    row = IssueReport(user_id=user.id, form_key=uuid4(), category=category, status=status, text='It broke.',
                      created_at=datetime.now(UTC) - timedelta(minutes=age_minutes), **fields)
    db.session.add(row)
    db.session.flush()
    return row


def call(rh_class, user, monkeypatch, *, args=None, json=None, **view_args):
    request = MagicMock()
    request.args = args or {}
    request.get_json.return_value = json
    request.view_args = view_args
    monkeypatch.setattr(reports_module, 'request', request)
    rh = rh_class.__new__(rh_class)
    rh._user = user
    response, status = rh._process()
    return status, response.get_json()


def test_the_list_is_paged_newest_first_and_counts_the_open(db, users, monkeypatch):
    rows = [filed(db, users['makoto'], status='closed' if i % 3 == 0 else 'open', age_minutes=i) for i in range(120)]
    status, first = call(RHAdminReportList, users['lucas'], monkeypatch)
    _, last = call(RHAdminReportList, users['lucas'], monkeypatch, args={'page': '3'})
    assert status == 200 and (first['page'], first['pages'], last['page']) == (1, 3, 3)
    assert [r['report_id'] for r in first['reports']] == [r.id for r in rows[:50]] and len(last['reports']) == 20
    assert first['open'] == 80 and first['reports'][0]['user'] == {'id': users['makoto'].id,
                                                                   'name': users['makoto'].full_name}


def test_the_list_filters_by_status_and_category(db, users, monkeypatch):
    wanted = filed(db, users['makoto'], category='wrong_answer', status='under_review')
    filed(db, users['makoto'], category='wrong_answer')
    filed(db, users['makoto'], category='bug', status='under_review')
    _, body = call(RHAdminReportList, users['lucas'], monkeypatch,
                   args={'status': 'under_review', 'category': 'wrong_answer'})
    assert [r['report_id'] for r in body['reports']] == [wanted.id]
    assert call(RHAdminReportList, users['lucas'], monkeypatch, args={'status': 'wontfix'})[0] == 422


def test_a_report_shows_everything_to_an_admin(db, users, monkeypatch):
    copy = {'messages': [{'id': 'a', 'role': 'assistant', 'content': 'x', 'evidence': {'intent': 'q'},
                          'sql_generated': 'SELECT 1'}]}
    row = filed(db, users['makoto'], copy=copy)
    status, body = call(RHAdminReportDetail, users['lucas'], monkeypatch, report_id=row.id)
    assert status == 200 and body['copy'] == copy and body['updated_by'] is None and body['closed_at'] is None
    assert body['user'] == {'id': users['makoto'].id, 'name': users['makoto'].full_name,
                            'email': users['makoto'].email}
    assert call(RHAdminReportDetail, users['lucas'], monkeypatch, report_id=row.id + 1000)[0] == 404


def save(users, monkeypatch, row, **body):
    return call(RHAdminReportUpdate, users['lucas'], monkeypatch, report_id=row.id, json=body)


def test_a_save_records_who_and_when_and_closing_follows_the_status(db, users, monkeypatch):
    row = filed(db, users['makoto'])
    status, body = save(users, monkeypatch, row, status='closed', note='Fixed in 1.2.', seen='')
    closed_at = row.closed_at
    assert status == 200 and (row.status, row.note, row.updated_by_id) == ('closed', 'Fixed in 1.2.', users['lucas'].id)
    assert closed_at is not None and body['updated_by'] == {'id': users['lucas'].id, 'name': users['lucas'].full_name}
    # a note-only save on a closed report keeps when it closed; reopening clears it (FR-020)
    save(users, monkeypatch, row, status='closed', note='Fixed in 1.2.1.', seen=row.updated_at.isoformat())
    assert row.closed_at == closed_at and row.note == 'Fixed in 1.2.1.'
    save(users, monkeypatch, row, status='under_review', note='', seen=row.updated_at.isoformat())
    assert (row.status, row.closed_at, row.note) == ('under_review', None, None)


def test_a_save_from_an_out_of_date_view_is_refused_and_changes_nothing(db, users, monkeypatch):
    row = filed(db, users['makoto'])
    save(users, monkeypatch, row, status='closed', note='Done.', seen='')  # the other admin's save
    status, body = save(users, monkeypatch, row, status='open', note='Looking.', seen='')  # made from the old page
    assert status == 409 and body['error'] == 'STALE' and body['details']['report']['status'] == 'closed'
    assert (row.status, row.note) == ('closed', 'Done.')


@pytest.mark.parametrize('bad', [{'status': 'wontfix'}, {'note': 'x' * 2001}])
def test_a_bad_save_is_refused(db, users, monkeypatch, bad):
    row = filed(db, users['makoto'])
    assert save(users, monkeypatch, row, **{'status': 'open', 'note': '', 'seen': '', **bad})[0] == 422
    assert row.updated_at is None


def test_every_admin_endpoint_refuses_a_non_admin_and_admits_an_admin(app, db, users):
    for rh_class in (RHAdminReportList, RHAdminReportDetail, RHAdminReportUpdate):
        with app.test_request_context():
            session.set_session_user(users['makoto'])
            with pytest.raises(Forbidden):
                rh_class()._check_access()
        with app.test_request_context():
            session.set_session_user(users['lucas'])
            rh_class()._check_access()  # (the read limit behind it is Redis-backed, as in the other RH tests)
