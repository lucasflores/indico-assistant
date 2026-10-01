"""Connected accounts (spec 023, US1): the profile page, GitHub's sign-in, and the JSON API.

Feature: 023-github-connector

The pages are Indico RHs, as spec 021's report pages are: Indico checks who may see a profile (``RHUserBase``) and
the CSRF token of every form POST. The sign-in is GitHub's web flow with a one-time ``state`` and PKCE, both kept
in the user's Indico session (server-side); the code is exchanged here, never in the browser (FR-003, FR-004).

An admin can see and remove another user's connection (Lucas, 2026-09-30), but never reads GitHub as that user:
their page lists no repositories.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from flask import flash, jsonify, redirect, request, session
from indico.core.plugins import url_for_plugin
from indico.modules.users.controllers import RHUserBase
from indico.web.menu import SideMenuItem
from indico.web.rh import RHProtected
from werkzeug.exceptions import Forbidden, NotFound

from indico_assistant.controllers.base import RHSessionCSRFBase
from indico_assistant.controllers.report_pages import _profile_url
from indico_assistant.models import Connection
from indico_assistant.services.connectors import github, store
from indico_assistant.services.connectors.github import GitHubError
from indico_assistant.views import WPConnections

MENU_ITEM = 'assistant_connections'
OAUTH_KEY = 'assistant_github_oauth'
SHOWN_REPOS = 20


def _settings():
    from indico_assistant.plugin import AssistantPlugin
    return AssistantPlugin.settings.get_all()


def profile_menu_item(user) -> SideMenuItem | None:
    """"Connected accounts": on your own profile while GitHub is on; on another's (an admin) while they have one."""
    if not user.can_be_modified(session.user):
        return None
    if user == session.user and not _settings().get('github_enabled'):
        return None
    if user != session.user and store.connection(user.id) is None:
        return None
    return SideMenuItem(MENU_ITEM, 'Connected accounts', _profile_url('assistant.user_connections', user), 30)


class RHConnectionsBase(RHUserBase):
    def _check_access(self):
        RHUserBase._check_access(self)  # (logged in and allowed this profile before anything is looked up)
        self.settings = _settings()
        self.own = self.user == session.user
        self.connection = store.connection(self.user.id)
        if not self.settings.get('github_enabled') and (self.own or self.connection is None):
            raise NotFound  # off: only an admin removing someone's existing connection gets here


class RHConnections(RHConnectionsBase):
    """The page: the account, what the assistant can see, and Connect or Disconnect (FR-005)."""

    def _process(self):
        repos = repo_count = None
        failed = False
        enabled = self.settings.get('github_enabled')
        if self.own and enabled and self.connection is not None and not self.connection.needs_renewal:
            access = store.token(self.user.id, github.app_for(self.settings))
            if access.state == store.OK:
                try:
                    with github.client_for(access.token, self.settings) as client:
                        repos, repo_count = github.repositories(client)
                except GitHubError:
                    failed = True
            self.connection = store.connection(self.user.id)  # (a refused refresh: it needs renewing now)
        app_url = (self.settings.get('github_app_url') or '').rstrip('/')
        return WPConnections.render_template(
            'connections.html', MENU_ITEM, user=self.user, own=self.own, enabled=enabled, connection=self.connection,
            repos=repos[:SHOWN_REPOS] if repos is not None else None, repo_count=repo_count, repos_failed=failed,
            add_url=f'{app_url}/installations/new' if app_url else None,
            connect_url=_profile_url('assistant.github_connect', self.user),
            disconnect_url=_profile_url('assistant.github_disconnect', self.user))


class RHConnect(RHConnectionsBase):
    """POST: off to GitHub to authorise the app, with a one-time state and a PKCE challenge."""

    def _check_access(self):
        RHConnectionsBase._check_access(self)
        if not self.own:
            raise Forbidden  # (no one connects GitHub for someone else)
        if not self.settings.get('github_enabled'):
            raise NotFound

    def _process(self):
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        session[OAUTH_KEY] = {'state': state, 'verifier': verifier, 'user_id': session.user.id}
        if github.fake_enabled():  # (dev mode: the fake approves at once)
            return redirect(url_for_plugin('assistant.github_callback', code='fake-code', state=state))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        return redirect(github.app_for(self.settings).authorize_url(github.callback_url(), state, challenge))


class RHGitHubCallback(RHProtected):
    """Where GitHub sends the user back: stores the connection only for the state this user's session holds."""

    def _process(self):
        saved = session.pop(OAUTH_KEY, None)
        state, code = request.args.get('state') or '', request.args.get('code')
        settings = _settings()
        if (not saved or saved.get('user_id') != session.user.id
                or not hmac.compare_digest(saved.get('state', ''), state)):
            flash("GitHub wasn't connected: the sign-in couldn't be checked. Please try again.", 'error')
        elif request.args.get('error') or not code or not settings.get('github_enabled'):
            flash("GitHub wasn't connected.", 'warning')
        else:
            app = github.app_for(settings)
            try:
                tokens = app.exchange(code, saved['verifier'], github.callback_url())
                account = app.account(tokens.access)
            except GitHubError as error:
                flash(f"GitHub wasn't connected: {error.message}", 'error')
            else:
                store.save(session.user.id, 'github', account, tokens)
                flash(f'GitHub is connected as @{account.login}.', 'success')
        return redirect(url_for_plugin('assistant.user_connections'))


class RHDisconnect(RHConnectionsBase):
    """POST: the user, or an admin on their profile, removes the connection (FR-007)."""

    def _process(self):
        store.disconnect(self.user.id, github.app_for(self.settings))
        flash('GitHub is disconnected.', 'success')
        return redirect(_profile_url('assistant.user_connections', self.user))


# --- the API -----------------------------------------------------------------------------------------------

def _summary(row: Connection) -> dict:
    """A connection as the API shows it: never a token (FR-009)."""
    return {'service': row.service, 'login': row.account_login, 'connected_at': row.connected_at.isoformat(),
            'last_used_at': row.last_used_at.isoformat() if row.last_used_at else None,
            'needs_renewal': row.needs_renewal}


class RHConnectionsAPI(RHSessionCSRFBase):
    """GET /connections: the caller's connected accounts."""

    RATE_LIMIT = "read"

    def _process(self):
        rows = Connection.query.filter_by(user_id=self.user.id).order_by(Connection.service).all()
        return jsonify({'connections': [_summary(row) for row in rows]}), 200


class RHConnectionDelete(RHSessionCSRFBase):
    """DELETE /connections/<service>: disconnect, as the page's Disconnect does."""

    RATE_LIMIT = "read"

    def _process(self):
        service = request.view_args['service']
        if service != 'github' or store.connection(self.user.id, service) is None:
            return self._not_found_error("Connection")
        store.disconnect(self.user.id, github.app_for(_settings()))
        return jsonify({'deleted': True}), 200
