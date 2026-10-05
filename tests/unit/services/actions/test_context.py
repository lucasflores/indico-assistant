"""Running Indico code as the chat user outside a web request (research R1)."""

from datetime import datetime

import pytest
import pytz
from flask import session


from indico_assistant.services.actions.context import acting_as, local_today, user_timezone


@pytest.fixture
def memoized(app, monkeypatch):
    """Production behaviour: Indico only memoizes per request when not TESTING."""
    monkeypatch.setitem(app.config, "TESTING", False)


def test_acting_as_sets_the_session_user_with_request_memoization_on(request_context, memoized, dummy_user):
    with acting_as(dummy_user):
        assert session.user == dummy_user
    assert session.user is None  # restored afterwards


def test_set_session_user_is_not_enough_here(request_context, memoized, dummy_user):
    # Why acting_as exists: set_session_user() looks up the current user first, which caches "nobody"
    # for the rest of the request, so session.user stays None.
    session.set_session_user(dummy_user)
    assert session.user is None


def test_blocked_or_deleted_users_cannot_act(request_context, dummy_user):
    dummy_user.is_blocked = True
    with pytest.raises(PermissionError):
        with acting_as(dummy_user):
            pass


def test_needs_a_request_context(dummy_user, monkeypatch):
    # (the plugin's conftest pushes a request context for every test, so simulate a bare worker)
    monkeypatch.setattr("indico_assistant.services.actions.context.has_request_context", lambda: False)
    with pytest.raises(RuntimeError):
        with acting_as(dummy_user):
            pass


def test_user_timezone_and_today(dummy_user, monkeypatch):
    dummy_user.settings.set("timezone", "Asia/Tokyo")
    assert user_timezone(dummy_user) == pytz.timezone("Asia/Tokyo")
    fixed = datetime(2026, 9, 27, 20, 0, tzinfo=pytz.utc)  # already the 28th in Tokyo
    monkeypatch.setattr("indico_assistant.services.actions.context.now_utc", lambda: fixed)
    assert str(local_today(dummy_user)) == "2026-09-28"

    dummy_user.settings.delete("timezone")
    from indico.core.config import config

    assert user_timezone(dummy_user) == pytz.timezone(config.DEFAULT_TIMEZONE)


def test_a_failed_switch_still_restores_the_session(request_context, memoized, dummy_user):
    """(spec 025 live window: a user acting_as could not switch to left the session pointing at them, and every
    later access check in the same request saw nobody)"""
    from unittest.mock import MagicMock

    ghost = MagicMock(id=987654, is_deleted=False, is_blocked=False)  # (no such user: session.user stays None)
    ghost.settings.get.return_value = None
    with acting_as(dummy_user):
        with pytest.raises(RuntimeError):
            with acting_as(ghost):
                pass
        assert session.user == dummy_user  # the outer user, restored
    assert session.user is None
