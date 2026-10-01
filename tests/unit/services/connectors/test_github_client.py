"""The GitHub client and the app's OAuth calls (spec 023, T006), against httpx's mock transport."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from indico_assistant.services.connectors.github import GitHubClient, GitHubError, OAuthApp

TOKEN = "ghu_known-test-token"


def recording(responses):
    """A transport answering each request with the next of ``responses``; the requests are kept."""
    seen = []

    def handle(request):
        seen.append(request)
        status, body = responses.pop(0)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handle), seen


def test_a_call_carries_the_token_in_its_header_only():
    transport, seen = recording([(200, {"login": "octo"})])
    assert GitHubClient(TOKEN, transport=transport).get("/user") == {"login": "octo"}
    (request,) = seen
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["Accept"] == "application/vnd.github+json" and request.headers["X-GitHub-Api-Version"]
    assert TOKEN not in str(request.url)


@pytest.mark.parametrize("status", [401, 404, 422, 500])
def test_an_error_carries_githubs_message_never_the_token(status):
    transport, _ = recording([(status, {"message": "Bad credentials"})])
    with pytest.raises(GitHubError) as error:
        GitHubClient(TOKEN, transport=transport).get("/user")
    assert error.value.status == status and "Bad credentials" in str(error.value)
    assert TOKEN not in str(error.value)


def test_a_timeout_is_an_error_too():
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(GitHubError, match="in time"):
        GitHubClient(TOKEN, transport=httpx.MockTransport(slow)).get("/user")


def test_the_authorize_url_asks_with_state_and_pkce():
    url = OAuthApp("Iv1.abc", "s3cret").authorize_url("https://indico.test/assistant/github/callback", "st4te", "ch4l")
    parts = urlsplit(url)
    assert (parts.netloc, parts.path) == ("github.com", "/login/oauth/authorize")
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert query == {"client_id": "Iv1.abc", "redirect_uri": "https://indico.test/assistant/github/callback",
                     "state": "st4te", "code_challenge": "ch4l", "code_challenge_method": "S256"}
    assert "s3cret" not in url


def test_exchange_posts_the_code_and_verifier_in_the_body_and_reads_both_expiries():
    transport, seen = recording([(200, {"access_token": TOKEN, "expires_in": 28800, "refresh_token": "ghr_r",
                                        "refresh_token_expires_in": 15897600, "token_type": "bearer"})])
    before = datetime.now(UTC)
    tokens = OAuthApp("Iv1.abc", "s3cret", transport=transport).exchange("c0de", "v3rifier", "https://cb")
    (request,) = seen
    assert request.method == "POST" and request.url.path == "/login/oauth/access_token" and not request.url.query
    assert request.headers["Accept"] == "application/json"
    body = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
    assert body == {"client_id": "Iv1.abc", "client_secret": "s3cret", "code": "c0de", "code_verifier": "v3rifier",
                    "redirect_uri": "https://cb"}
    assert (tokens.access, tokens.refresh) == (TOKEN, "ghr_r")
    assert before + timedelta(hours=8) <= tokens.access_expires_at <= datetime.now(UTC) + timedelta(hours=8)
    assert tokens.refresh_expires_at - tokens.access_expires_at > timedelta(days=180)


def test_refresh_posts_the_refresh_token():
    transport, seen = recording([(200, {"access_token": "ghu_new", "expires_in": 28800, "refresh_token": "ghr_new",
                                        "refresh_token_expires_in": 15897600})])
    assert OAuthApp("Iv1.abc", "s3cret", transport=transport).refresh("ghr_old").access == "ghu_new"
    body = {k: v[0] for k, v in parse_qs(seen[0].content.decode()).items()}
    assert body == {"client_id": "Iv1.abc", "client_secret": "s3cret", "grant_type": "refresh_token",
                    "refresh_token": "ghr_old"}


def test_githubs_oauth_errors_come_as_200s_and_are_raised():
    transport, _ = recording([(200, {"error": "bad_refresh_token", "error_description": "The refresh token is bad"})])
    with pytest.raises(GitHubError, match="bad_refresh_token"):
        OAuthApp("Iv1.abc", "s3cret", transport=transport).refresh("ghr_old")


def test_a_token_that_never_expires_has_no_expiry():
    transport, _ = recording([(200, {"access_token": TOKEN, "token_type": "bearer"})])
    tokens = OAuthApp("Iv1.abc", "s3cret", transport=transport).exchange("c0de", "v", "https://cb")
    assert (tokens.access_expires_at, tokens.refresh, tokens.refresh_expires_at) == (None, None, None)


def test_revoke_deletes_the_grant_with_the_apps_credentials():
    transport, seen = recording([(204, None)])
    OAuthApp("Iv1.abc", "s3cret", transport=transport).revoke(TOKEN)
    (request,) = seen
    assert request.method == "DELETE" and request.url.path == "/applications/Iv1.abc/grant"
    assert request.headers["Authorization"].startswith("Basic ") and TOKEN not in str(request.url)
    assert TOKEN in request.content.decode()
