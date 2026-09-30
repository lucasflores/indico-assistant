"""Sending a report: POST /reports (spec 021, US1) and the API base it stands on."""

import pytest
from flask import session
from werkzeug.exceptions import BadRequest

from indico_assistant.controllers.reports import RHReportsAPI


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
