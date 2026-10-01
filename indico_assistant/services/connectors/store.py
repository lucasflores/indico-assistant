"""The connections' tokens, encrypted at rest (spec 023, FR-008 to FR-010).

Nothing else decrypts a token. The key is a Fernet key in an environment variable, as the Teams plugin reads its own
secrets (Indico drops unknown ``indico.conf`` keys); the web server stores the tokens and the worker reads them, so
both need it.

A token is never logged: a failure is logged by what failed, with GitHub's message (which never carries a token).
"""

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from indico.core.db import db

from indico_assistant.models import Connection
from indico_assistant.services.connectors.github import Account, GitHubError

logger = logging.getLogger(__name__)

KEY_ENV = "INDICO_ASSISTANT_CONNECTOR_KEY"
#: An access token with less left than this is refreshed first: an answer's loop runs for up to a minute.
MARGIN = timedelta(minutes=5)
OK, NOT_CONNECTED, RENEW, UNAVAILABLE = "ok", "not connected", "renew", "unavailable"


@dataclass(frozen=True)
class Access:
    token: str | None
    state: str  # OK | NOT_CONNECTED | RENEW | UNAVAILABLE (GitHub didn't answer the refresh: try again later)


def fernet():
    """The tokens' Fernet, or None when the key is missing or not a Fernet key."""
    from cryptography.fernet import Fernet

    key = os.environ.get(KEY_ENV, "").strip()
    try:
        return Fernet(key) if key else None
    except ValueError:
        return None


def connection(user_id, service="github"):
    return Connection.query.filter_by(user_id=user_id, service=service).first()


def _fresh(row):
    return row.access_expires_at is None or row.access_expires_at > datetime.now(UTC) + MARGIN


def _renew(row):
    row.needs_renewal = True
    db.session.commit()
    return Access(None, RENEW)


def _transient(error):
    """GitHub didn't answer, was overloaded or rate-limited: the refresh token may still be good."""
    return error.status in (0, 429) or error.status >= 500


def renew(user_id, service="github"):
    """GitHub refused a token it had issued (401: the grant was revoked there): the user must connect again."""
    if row := connection(user_id, service):
        _renew(row)


def save(user_id, service, account, tokens):
    """Store a new connection, or replace the user's one (reconnecting renews it)."""
    box = fernet()
    if box is None:
        raise RuntimeError(f"{KEY_ENV} is not set")
    row = connection(user_id, service) or Connection(user_id=user_id, service=service)
    row.account_id, row.account_login = account.id, account.login
    row.access_token = box.encrypt(tokens.access.encode()).decode()
    row.refresh_token = box.encrypt(tokens.refresh.encode()).decode() if tokens.refresh else None
    row.access_expires_at, row.refresh_expires_at = tokens.access_expires_at, tokens.refresh_expires_at
    row.connected_at, row.needs_renewal = datetime.now(UTC), False
    db.session.add(row)
    db.session.flush()
    return row


def token(user_id, app, service="github"):
    """The user's access token, refreshed first when it is about to expire.

    GitHub's refresh tokens are single-use: two answers refreshing at once would leave one of them holding a dead
    pair, so the refresh runs under a lock on the row, and the expiry is read again once it is held (another worker
    may just have refreshed). The lock is held through one HTTP call to GitHub.
    """
    from cryptography.fernet import InvalidToken

    row = connection(user_id, service)
    if row is None:
        return Access(None, NOT_CONNECTED)
    if row.needs_renewal:
        return Access(None, RENEW)
    box = fernet()
    if box is None:  # (GitHub can't be turned on without it: it was removed since)
        logger.error("%s is not set: the stored %s connections can't be read", KEY_ENV, service)
        return Access(None, NOT_CONNECTED)
    try:
        if _fresh(row):
            return Access(box.decrypt(row.access_token.encode()).decode(), OK)
        # ponytail: a row lock held through GitHub's refresh call (~0.5 s); fine at one refresh per user per 8 h
        row = Connection.query.filter_by(id=row.id).populate_existing().with_for_update().one()
        if _fresh(row):
            access = box.decrypt(row.access_token.encode()).decode()
            db.session.commit()  # (releases the lock)
            return Access(access, OK)
        if not row.refresh_token or (row.refresh_expires_at and row.refresh_expires_at <= datetime.now(UTC)):
            return _renew(row)
        refresh = box.decrypt(row.refresh_token.encode()).decode()
    except InvalidToken:  # the key changed: what is stored can't be read any more
        logger.warning("A stored %s connection no longer decrypts (the key changed?): it needs renewing", service)
        return _renew(row)
    try:
        tokens = app.refresh(refresh)
    except GitHubError as error:
        if _transient(error):  # (Copilot, PR #17: an outage must not make everyone reconnect)
            logger.warning("GitHub didn't refresh a connection (%s %s): kept, try again later", error.status,
                           error.message)
            db.session.commit()  # (releases the lock)
            return Access(None, UNAVAILABLE)
        logger.info("GitHub refused to refresh a connection (%s): it needs renewing", error.message)
        return _renew(row)
    save(user_id, service, Account(row.account_id, row.account_login), tokens)
    db.session.commit()
    return Access(tokens.access, OK)


def disconnect(user_id, app, service="github"):
    """Delete the connection now, then ask GitHub to revoke the grant (best effort: the delete stands either way)."""
    from cryptography.fernet import InvalidToken

    row = connection(user_id, service)
    if row is None:
        return
    box = fernet()
    try:
        access = box.decrypt(row.access_token.encode()).decode() if box else None
    except InvalidToken:
        access = None
    db.session.delete(row)
    db.session.commit()
    if access is None or not app.client_id:
        return  # (no app configured any more: nothing to revoke with)
    try:
        app.revoke(access)
    except GitHubError as error:
        logger.warning("GitHub didn't revoke a disconnected grant (%s); the connection is deleted", error.message)
    except Exception as error:  # noqa: BLE001 - best effort, after the delete (Copilot, PR #17): never a 500
        logger.warning("Revoking a disconnected grant failed (%s); the connection is deleted", type(error).__name__)


def merged(target_id, source_id):
    """Merged accounts (Indico's ``users.merged``): the merged account's connections move to the one that remains,
    unless it already has one for that service."""
    for row in Connection.query.filter_by(user_id=source_id).all():
        if connection(target_id, row.service):
            db.session.delete(row)
        else:
            row.user_id = target_id
    db.session.flush()


def forget(user_id):
    """A deleted or anonymised account (Indico's ``users.db_deleted`` / ``users.anonymized``)."""
    Connection.query.filter_by(user_id=user_id).delete()
    db.session.flush()


def used(user_id, service="github"):
    """The connection was just used for an answer (the page shows when): committed before the loop's model calls."""
    if row := connection(user_id, service):
        row.last_used_at = datetime.now(UTC)
    db.session.commit()
