"""The report pages (spec 021): the user's profile page (US2) and the admins' triage page (US3).

The RHs run with Indico's own access checks (RHUserBase, RHAdminBase) in a request context; the template
rendering is captured instead of drawn (the pages themselves are checked live, T028 and T036).
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from flask import request, session
from werkzeug.exceptions import Forbidden, NotFound

import indico_assistant.controllers.report_pages as pages
from indico_assistant.models import IssueReport
from indico_assistant.views import WPReports


@pytest.fixture
def users(create_user):
    return {'lucas': create_user(20, first_name='Lucas', admin=True), 'makoto': create_user(21, first_name='Makoto')}


@pytest.fixture
def rendered(monkeypatch):
    seen = {}

    def render(template, *wp_args, **context):
        seen.update(template=template, wp_args=wp_args, **context)
        return 'page'

    monkeypatch.setattr(WPReports, 'render_template', staticmethod(render))
    monkeypatch.setattr(pages, 'url_for_plugin', lambda endpoint, **kw: f'/{endpoint}/{kw}')
    monkeypatch.setattr(pages, 'flash', MagicMock())
    return seen


def filed(db, user, copy=None):
    row = IssueReport(user_id=user.id, form_key=uuid4(), category='bug', text='It broke.', copy=copy)
    db.session.add(row)
    db.session.flush()
    return row


def run(app, rh_class, viewer, method='GET', **view_args):
    """Process ``rh_class`` as Indico would after routing: arguments, access, then the page."""
    with app.test_request_context(method=method):
        request.view_args = view_args
        session.set_session_user(viewer)
        rh = rh_class()
        rh._process_args()
        rh._check_access()
        return rh._process()


# --- US2: the profile page (T022) -------------------------------------------------------------------------

def test_your_own_list(app, db, users, rendered):
    mine = filed(db, users['makoto'])
    filed(db, users['lucas'])
    assert run(app, pages.RHUserReports, users['makoto']) == 'page'
    assert rendered['template'] == 'reports.html' and rendered['wp_args'][-1] == 'assistant_reports'
    assert rendered['reports'] == [mine] and rendered['user'] == users['makoto']


def test_someone_elses_profile_is_refused_to_a_non_admin(app, db, users, rendered):
    with pytest.raises(Forbidden):
        run(app, pages.RHUserReports, users['makoto'], user_id=users['lucas'].id)


def test_an_admin_sees_someone_elses_reports_but_cannot_delete_them(app, db, users, rendered):
    theirs = filed(db, users['makoto'])
    run(app, pages.RHUserReports, users['lucas'], user_id=users['makoto'].id)
    assert rendered['reports'] == [theirs]
    run(app, pages.RHUserReport, users['lucas'], user_id=users['makoto'].id, report_id=theirs.id)
    assert rendered['can_delete'] is False
    with pytest.raises(Forbidden):
        run(app, pages.RHUserReportDelete, users['lucas'], 'POST', user_id=users['makoto'].id, report_id=theirs.id)
    assert db.session.get(IssueReport, theirs.id) is not None


def test_a_report_page_shows_the_users_view(app, db, users, rendered):
    row = filed(db, users['makoto'], copy={'taken_at': 't', 'reported_answer_id': None, 'truncated': False,
                                           'messages': [{'id': 'a', 'role': 'assistant', 'content': 'x',
                                                         'created_at': 't', 'evidence': {'intent': 'y'}}]})
    run(app, pages.RHUserReport, users['makoto'], report_id=row.id)
    assert rendered['template'] == 'report.html' and rendered['can_delete'] is True
    assert rendered['report'] == row and rendered['copy']['messages'] == [{'id': 'a', 'role': 'assistant',
                                                                           'content': 'x', 'created_at': 't'}]


def test_someone_elses_report_under_your_profile_is_not_found(app, db, users, rendered):
    theirs = filed(db, users['lucas'])
    with pytest.raises(NotFound):
        run(app, pages.RHUserReport, users['makoto'], report_id=theirs.id)


def test_the_reporter_deletes_and_goes_back_to_the_list(app, db, users, rendered):
    row = filed(db, users['makoto'])
    response = run(app, pages.RHUserReportDelete, users['makoto'], 'POST', report_id=row.id)
    assert response.status_code == 302 and db.session.get(IssueReport, row.id) is None
    pages.flash.assert_called_once()


def test_the_profile_menu_shows_the_item_once_there_is_a_report(app, db, users, rendered):
    with app.test_request_context():
        session.set_session_user(users['makoto'])
        assert pages.profile_menu_item(users['makoto']) is None
        filed(db, users['makoto'])
        item = pages.profile_menu_item(users['makoto'])
        assert item.name == 'assistant_reports' and item.title == 'Assistant reports'
        assert pages.profile_menu_item(users['lucas']) is None  # someone else's profile, and not an admin
