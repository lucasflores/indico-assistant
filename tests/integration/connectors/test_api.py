"""The connections API (spec 023, US1: T015): list and remove; connecting needs the browser."""

from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

import indico_assistant.controllers.connections as connections
from indico_assistant.controllers.base import RHSessionCSRFBase
from indico_assistant.models import Connection
from indico_assistant.services.connectors import github, store
from indico_assistant.services.connectors.fake_github import FakeGitHub

SETTINGS = {"github_enabled": True, "github_client_id": "Iv1.fake", "github_client_secret": "fake-secret"}


@pytest.fixture
def users(create_user):
    return {'lucas': create_user(20, admin=True), 'makoto': create_user(21)}


@pytest.fixture
def connected(db, users, tmp_path, monkeypatch):
    fake = FakeGitHub(tmp_path / "fake.json")
    monkeypatch.setattr(github, "_transport", fake.transport)
    monkeypatch.setattr(connections, "_settings", lambda: SETTINGS)
    monkeypatch.setenv(store.KEY_ENV, Fernet.generate_key().decode())
    app = github.app_for(SETTINGS)
    tokens = app.exchange("fake-code", "v", "https://cb")
    store.save(users['makoto'].id, "github", app.account(tokens.access), tokens)
    db.session.flush()
    return tokens


def call(rh_class, user, monkeypatch, **view_args):
    request = MagicMock()
    request.view_args = view_args
    monkeypatch.setattr(connections, 'request', request)
    rh = rh_class.__new__(rh_class)
    rh._user = user
    response, status = rh._process()
    return status, response.get_json()


def test_the_list_has_no_token(db, users, connected, monkeypatch):
    status, body = call(connections.RHConnectionsAPI, users['makoto'], monkeypatch)
    (row,) = body['connections']
    assert status == 200 and row['service'] == 'github' and row['login'] == 'octo-dev'
    assert set(row) == {'service', 'login', 'connected_at', 'last_used_at', 'needs_renewal'}
    assert connected.access not in str(body) and connected.refresh not in str(body)
    assert call(connections.RHConnectionsAPI, users['lucas'], monkeypatch) == (200, {'connections': []})


def test_delete_disconnects_only_your_own(db, users, connected, monkeypatch):
    status, _ = call(connections.RHConnectionDelete, users['lucas'], monkeypatch, service='github')
    assert status == 404 and Connection.query.count() == 1  # (Lucas has none; Makoto's is out of his reach)
    status, body = call(connections.RHConnectionDelete, users['makoto'], monkeypatch, service='github')
    assert (status, body) == (200, {'deleted': True}) and Connection.query.count() == 0
    assert call(connections.RHConnectionDelete, users['makoto'], monkeypatch, service='gitlab')[0] == 404


def test_the_cookie_needs_the_csrf_token_and_the_panels_token_does_not(app, db, users):
    """The rule of the report writes (spec 021 R10), shared through RHSessionCSRFBase."""
    from flask import session
    from werkzeug.exceptions import BadRequest

    def check(user=None, header=None):
        with app.test_request_context(method='DELETE', headers={'X-CSRF-Token': header} if header else {}):
            if user is not None:
                session.set_session_user(user)
                session['_csrf_token'] = 'the-real-one'
            connections.RHConnectionDelete()._check_csrf()

    assert issubclass(connections.RHConnectionsAPI, RHSessionCSRFBase)
    with pytest.raises(BadRequest):
        check(users['makoto'])
    check(users['makoto'], header='the-real-one')
    check()  # (a token call, X-Assistant-Auth, carries no cookie)
