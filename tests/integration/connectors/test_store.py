"""The token store (spec 023, T007): encrypted at rest, refreshed under a lock, and the account signals."""

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm.attributes import set_committed_value

from indico_assistant.models import Connection
from indico_assistant.services.connectors import store
from indico_assistant.services.connectors.fake_github import FakeGitHub
from indico_assistant.services.connectors.github import Account, OAuthApp, Tokens


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv(store.KEY_ENV, Fernet.generate_key().decode())


@pytest.fixture
def fake(tmp_path):
    return FakeGitHub(tmp_path / "fake.json")


@pytest.fixture
def github_app(fake):
    return OAuthApp("Iv1.fake", "fake-secret", transport=fake.transport())


@pytest.fixture
def users(create_user):
    return {'lucas': create_user(20, admin=True), 'makoto': create_user(21)}


def connected(db, user, github_app, **expiry):
    tokens = github_app.exchange("fake-code", "v", "https://cb")
    if expiry:
        tokens = Tokens(tokens.access, expiry.get("access"), tokens.refresh, expiry.get("refresh",
                                                                                     tokens.refresh_expires_at))
    store.save(user.id, "github", Account(1001, "octo-dev"), tokens)
    db.session.flush()
    return tokens


def row(user):
    return Connection.query.filter_by(user_id=user.id, service="github").one()


def test_saved_tokens_are_ciphertext_and_come_back(db, users, github_app):
    tokens = connected(db, users['makoto'], github_app)
    saved = row(users['makoto'])
    assert tokens.access not in saved.access_token and tokens.refresh not in saved.refresh_token
    assert store.token(users['makoto'].id, github_app) == store.Access(tokens.access, store.OK)


def test_saving_again_replaces_the_connection(db, users, github_app):
    connected(db, users['makoto'], github_app)
    row(users['makoto']).needs_renewal = True
    newer = connected(db, users['makoto'], github_app)
    assert Connection.query.filter_by(user_id=users['makoto'].id).count() == 1
    assert store.token(users['makoto'].id, github_app).token == newer.access


def test_not_connected(db, users, github_app):
    assert store.token(users['makoto'].id, github_app) == store.Access(None, store.NOT_CONNECTED)


def test_a_token_about_to_expire_is_refreshed_once_and_saved(db, users, github_app, fake):
    old = connected(db, users['makoto'], github_app, access=datetime.now(UTC) + timedelta(minutes=2))
    access = store.token(users['makoto'].id, github_app)
    assert access.state == store.OK and access.token != old.access
    assert row(users['makoto']).access_expires_at > datetime.now(UTC) + timedelta(hours=7)
    assert store.token(users['makoto'].id, github_app).token == access.token  # (fresh now: no second refresh)
    assert [c for c in fake.calls if c == ("POST", "/login/oauth/access_token")] == [("POST", "/login/oauth/access_token")] * 2


def test_a_refresh_someone_else_just_made_is_seen_under_the_lock(db, users, github_app, fake):
    connected(db, users['makoto'], github_app)  # fresh in the database...
    set_committed_value(row(users['makoto']), 'access_expires_at', datetime.now(UTC))  # ...stale in this session
    before = len(fake.calls)
    assert store.token(users['makoto'].id, github_app).state == store.OK
    assert ("POST", "/login/oauth/access_token") not in fake.calls[before:]  # re-read under the lock: no refresh


def test_a_refused_refresh_needs_renewal(db, users, github_app, fake):
    connected(db, users['makoto'], github_app, access=datetime.now(UTC))
    fake.refuse_refresh()
    assert store.token(users['makoto'].id, github_app) == store.Access(None, store.RENEW)
    assert row(users['makoto']).needs_renewal
    assert store.token(users['makoto'].id, github_app).state == store.RENEW  # (and stays so, with no more calls)


def test_an_expired_refresh_token_needs_renewal_without_asking_github(db, users, github_app, fake):
    connected(db, users['makoto'], github_app, access=datetime.now(UTC), refresh=datetime.now(UTC) - timedelta(days=1))
    before = len(fake.calls)
    assert store.token(users['makoto'].id, github_app).state == store.RENEW and fake.calls[before:] == []


def test_a_changed_key_needs_renewal_not_an_error(db, users, github_app, monkeypatch):
    connected(db, users['makoto'], github_app)
    monkeypatch.setenv(store.KEY_ENV, Fernet.generate_key().decode())
    assert store.token(users['makoto'].id, github_app).state == store.RENEW


def test_no_key_is_not_connected(db, users, github_app, monkeypatch):
    connected(db, users['makoto'], github_app)
    monkeypatch.delenv(store.KEY_ENV)
    assert store.token(users['makoto'].id, github_app).state == store.NOT_CONNECTED
    assert not row(users['makoto']).needs_renewal  # (the key comes back: the connection works again)


def test_disconnect_deletes_and_revokes(db, users, github_app, fake):
    tokens = connected(db, users['makoto'], github_app)
    store.disconnect(users['makoto'].id, github_app)
    assert Connection.query.filter_by(user_id=users['makoto'].id).count() == 0
    assert ("DELETE", "/applications/Iv1.fake/grant") in fake.calls
    assert tokens.access not in fake.state["tokens"]


def test_disconnect_deletes_even_when_github_fails(db, users, github_app, fake, caplog):
    tokens = connected(db, users['makoto'], github_app)
    fake.fail_next("/applications/Iv1.fake/grant", 500)
    store.disconnect(users['makoto'].id, github_app)
    assert Connection.query.filter_by(user_id=users['makoto'].id).count() == 0
    assert tokens.access not in caplog.text


def test_merged_accounts_keep_one_connection(db, users, github_app, create_user):
    makoto, lucas, other = users['makoto'], users['lucas'], create_user(22)
    connected(db, makoto, github_app)
    store.merged(other.id, makoto.id)  # the target has none: it moves
    assert row(other) and not Connection.query.filter_by(user_id=makoto.id).count()
    connected(db, lucas, github_app)
    store.merged(other.id, lucas.id)  # the target has one: the merged account's goes
    assert Connection.query.filter_by(service="github").count() == 1 and row(other)


def test_forget_deletes(db, users, github_app):
    connected(db, users['makoto'], github_app)
    store.forget(users['makoto'].id)
    assert Connection.query.filter_by(user_id=users['makoto'].id).count() == 0


def test_indicos_account_signals_reach_the_store(db, users, github_app, create_user):
    from indico_assistant.plugin import _forget_connections, _merge_connections

    makoto, other = users['makoto'], create_user(22)
    connected(db, makoto, github_app)
    _merge_connections(other, source=makoto)
    assert row(other)
    _forget_connections(other, flushed=False)  # (before the flush: it may still fail)
    assert row(other)
    _forget_connections(other, flushed=True)
    assert not Connection.query.filter_by(user_id=other.id).count()
