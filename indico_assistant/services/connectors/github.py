"""GitHub, read with the user's own token (spec 023): the client, the app's OAuth calls, and the read tools.

The token only ever travels in a header (FR-009): never in a URL, and never in an error's message. The OAuth calls
send their secrets in the request body, not the query string.
"""

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

API = "https://api.github.com"
WEB = "https://github.com"
API_VERSION = "2022-11-28"
#: The one fixed callback of the instance's GitHub App (registered there; outside the profile's per-user URLs).
CALLBACK_PATH = "/assistant/github/callback"
#: Dev mode (FR-020): with DEBUG on, the fake GitHub answers instead of github.com, as the Teams plugin's fake Graph.
FAKE_ENV = "INDICO_ASSISTANT_FAKE_GITHUB"


def callback_url():
    from indico.core.config import config

    return config.BASE_URL.rstrip("/") + CALLBACK_PATH


class GitHubError(Exception):
    """A call GitHub refused or didn't answer (``status`` 0). The message is GitHub's, never the token."""

    def __init__(self, status, message):
        super().__init__(f"GitHub {status or 'unreachable'}: {message}")
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Tokens:
    access: str
    access_expires_at: datetime | None  # None: the app's tokens don't expire
    refresh: str | None
    refresh_expires_at: datetime | None


@dataclass(frozen=True)
class Account:
    id: int
    login: str


def _send(http, method, url, **kwargs):
    try:
        response = http.request(method, url, **kwargs)
    except httpx.TimeoutException:
        raise GitHubError(0, "GitHub did not answer in time") from None
    except httpx.HTTPError:
        raise GitHubError(0, "GitHub could not be reached") from None
    if response.status_code >= 400:
        try:
            message = response.json().get("message") or response.reason_phrase
        except (ValueError, AttributeError):
            message = response.reason_phrase
        raise GitHubError(response.status_code, message)
    return response


class GitHubClient:
    """GitHub's REST API as one user. One per answer: ``with GitHubClient(...) as client``."""

    def __init__(self, token, *, timeout=10, transport=None):
        self._http = httpx.Client(base_url=API, timeout=timeout, transport=transport, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION})

    def get(self, path, params=None):
        return _send(self._http, "GET", path, params=params).json()

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class OAuthApp:
    """The instance's GitHub App, signing users in with GitHub's web flow (state + PKCE)."""

    def __init__(self, client_id, client_secret, *, timeout=10, transport=None):
        self.client_id, self._secret = client_id, client_secret
        self._timeout, self._transport = timeout, transport

    def authorize_url(self, redirect_uri, state, challenge):
        return f"{WEB}/login/oauth/authorize?" + urlencode({
            "client_id": self.client_id, "redirect_uri": redirect_uri, "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256"})

    def exchange(self, code, verifier, redirect_uri):
        return self._tokens({"code": code, "code_verifier": verifier, "redirect_uri": redirect_uri})

    def refresh(self, refresh_token):
        return self._tokens({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def revoke(self, access_token):
        """Ends the user's authorisation of the app, and every token of it."""
        with httpx.Client(timeout=self._timeout, transport=self._transport) as http:
            _send(http, "DELETE", f"{API}/applications/{self.client_id}/grant", json={"access_token": access_token},
                  auth=(self.client_id, self._secret),
                  headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION})

    def account(self, access_token):
        with GitHubClient(access_token, timeout=self._timeout, transport=self._transport) as client:
            user = client.get("/user")
        return Account(user["id"], user["login"])

    def _tokens(self, fields):
        with httpx.Client(timeout=self._timeout, transport=self._transport) as http:
            body = _send(http, "POST", f"{WEB}/login/oauth/access_token", headers={"Accept": "application/json"},
                         data={"client_id": self.client_id, "client_secret": self._secret, **fields}).json()
        if "error" in body or "access_token" not in body:  # (GitHub answers OAuth errors with a 200)
            raise GitHubError(400, body.get("error") or "no token")
        now = datetime.now(UTC)

        def at(seconds):
            return now + timedelta(seconds=int(seconds)) if seconds else None

        return Tokens(body["access_token"], at(body.get("expires_in")), body.get("refresh_token"),
                      at(body.get("refresh_token_expires_in")))


def fake_enabled():
    from indico.core.config import config

    return bool(os.environ.get(FAKE_ENV)) and config.DEBUG


def _transport():
    if not fake_enabled():
        return None
    from indico.core.config import config

    from indico_assistant.services.connectors.fake_github import FakeGitHub
    return FakeGitHub(os.path.join(config.CACHE_DIR, "assistant_fake_github.json")).transport()


def app_for(settings):
    """The instance's app, from the settings (the fake one in dev mode)."""
    return OAuthApp(settings.get("github_client_id"), settings.get("github_client_secret"),
                    timeout=float(settings.get("github_timeout_seconds") or 10), transport=_transport())


def client_for(token, settings):
    return GitHubClient(token, timeout=float(settings.get("github_timeout_seconds") or 10), transport=_transport())
