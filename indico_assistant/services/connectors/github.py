"""GitHub, read with the user's own token (spec 023): the client, the app's OAuth calls, and the read tools.

The token only ever travels in a header (FR-009): never in a URL, and never in an error's message. The OAuth calls
send their secrets in the request body, not the query string.
"""

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlencode

import httpx
from pydantic import AfterValidator, BaseModel, Field

from indico_assistant.services.connectors import Tool

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


def repositories(client, limit=100):
    """The repositories the app can see for this user (those of its installations the user can reach), capped at
    ``limit``, and how many there are in all."""
    found, total = [], 0
    for installation in client.get("/user/installations", {"per_page": 100})["installations"]:
        page = client.get(f"/user/installations/{installation['id']}/repositories", {"per_page": 100})
        total += page["total_count"]
        found += page["repositories"]
    return found[:limit], total


# --- the read tools (FR-015) ---------------------------------------------------------------------------------
# Each tool's docstring is what the model reads about it. A repository name is checked to be owner/name or a bare
# name, so a name the model was steered to write can't reach another endpoint ("../user"); a bare name (live run 1:
# "in ibis-routing") is resolved among the user's own repositories.

_NAME = re.compile(r"[A-Za-z0-9_.-]+")


def _repo(value):
    parts = value.split("/")
    if len(parts) > 2 or any(part in (".", "..") or not _NAME.fullmatch(part) for part in parts):
        raise ValueError("a repository is owner/name, or the name of one of the user's repositories")
    return value


Repo = Annotated[str, AfterValidator(_repo), Field(
    description="owner/name, e.g. octo-org/hello-world, or just the name of one of the user's repositories")]


def _full(client, repo):
    """``repo`` as owner/name: a bare name is looked up among the repositories the app can see for this user."""
    if repo is None or "/" in repo:
        return repo
    names = [r["full_name"] for r in repositories(client)[0]]
    found = [name for name in names if name.split("/")[1].lower() == repo.lower()]
    if len(found) == 1:
        return found[0]
    raise GitHubError(404, f"{repo} could be any of: {', '.join(found)}" if found else
                      f"no repository named {repo} that the app can see (it sees: {', '.join(names) or 'none'})")


class MyPullRequestsArgs(BaseModel):
    """Pull requests the user opened: open by default, or closed (not merged), merged, or all."""
    tool: Literal["my_pull_requests"]
    state: Literal["open", "closed", "merged", "all"] = "open"
    repo: Repo | None = None


class ReviewRequestsArgs(BaseModel):
    """Open pull requests waiting for the user's review."""
    tool: Literal["review_requests"]


class MyIssuesArgs(BaseModel):
    """Issues assigned to the user: open by default, or closed, or all."""
    tool: Literal["my_issues"]
    state: Literal["open", "closed", "all"] = "open"
    repo: Repo | None = None


class SearchArgs(BaseModel):
    """Issues or pull requests (one kind per call) matching a GitHub search, e.g. "involves:@me timezone" or
    "repo:owner/name label:bug"."""
    tool: Literal["search"]
    kind: Literal["issue", "pull_request"]
    query: str = Field(..., max_length=200)


class ItemArgs(BaseModel):
    """One issue or pull request in full: its state, labels, description, recent comments and, for a pull request,
    its reviews."""
    tool: Literal["item"]
    repo: Repo
    number: int = Field(..., gt=0)


class ActivityArgs(BaseModel):
    """A repository's recent activity: pushes, pull requests, issues, reviews, comments and releases."""
    tool: Literal["repo_activity"]
    repo: Repo


class RepositoriesArgs(BaseModel):
    """The repositories the assistant can see for the user (those where the app is installed)."""
    tool: Literal["repositories"]


def _cut(text, limit):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _ago(iso):
    """How long ago, in words: the model is given ages, not dates to subtract."""
    if not iso:
        return "at an unknown time"
    days = (datetime.now(UTC) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 86400
    if days < 1:
        return "today"
    if days < 2:
        return "yesterday"
    if days < 14:
        return f"{int(days)} days ago"
    return f"{int(days // 7)} weeks ago" if days < 60 else f"{int(days // 30)} months ago"


def _line(item):
    """One issue or pull request from a search or an item, on one line, with its own address."""
    pull = item.get("pull_request")
    state = "merged" if pull and pull.get("merged_at") else item.get("state", "?")
    bits = [f"#{item['number']} {item['repository_url'].split('/repos/', 1)[1]}", f'"{_cut(item.get("title"), 120)}"',
            state + (" (draft)" if item.get("draft") else ""),
            f"opened {_ago(item.get('created_at'))} by {(item.get('user') or {}).get('login', '?')}"]
    if item.get("labels"):
        bits.append("labels: " + ", ".join(label["name"] for label in item["labels"]))
    if item.get("comments"):
        bits.append(f"{item['comments']} comments")
    return " · ".join(bits) + f" · {item['html_url']}"


def _search(client, q, what):
    data = client.get("/search/issues", {"q": q, "per_page": 20, "sort": "created", "order": "desc"})
    items, total = data.get("items") or [], data.get("total_count", 0)
    if not items:
        return f"No {what} found."
    shown = f" (the newest {len(items)} shown)" if total > len(items) else ""
    return "\n".join([f"{total} {what}{shown}:", *map(_line, items)])


def _query(*parts):
    return " ".join(p for p in parts if p)


def _my_pull_requests(client, args):
    state = {"open": "is:open", "closed": "is:closed is:unmerged", "merged": "is:merged", "all": ""}[args.state]
    repo = _full(client, args.repo)
    return _search(client, _query("is:pr author:@me", state, repo and f"repo:{repo}"), "pull requests opened by the user")


def _review_requests(client, args):
    return _search(client, "is:pr is:open review-requested:@me", "open pull requests waiting for the user's review")


def _my_issues(client, args):
    state = {"open": "is:open", "closed": "is:closed", "all": ""}[args.state]
    repo = _full(client, args.repo)
    return _search(client, _query("is:issue assignee:@me", state, repo and f"repo:{repo}"), "issues assigned to the user")


def _search_tool(client, args):
    kind = "is:pr" if args.kind == "pull_request" else "is:issue"
    return _search(client, f"{kind} {args.query}", "pull requests" if args.kind == "pull_request" else "issues")


def _item(client, args):
    base = f"/repos/{_full(client, args.repo)}"
    issue = client.get(f"{base}/issues/{args.number}")
    is_pull = bool(issue.get("pull_request"))
    lines = [_line(issue)]
    if is_pull:
        pull = client.get(f"{base}/pulls/{args.number}")
        asked = ", ".join(r["login"] for r in pull.get("requested_reviewers") or [])
        lines.append(f"From {pull['head']['ref']} into {pull['base']['ref']}"
                     + (f"; review requested from {asked}" if asked else ""))
    if issue.get("assignees"):
        lines.append("Assigned to " + ", ".join(a["login"] for a in issue["assignees"]))
    if issue.get("body"):
        lines.append("Description: " + _cut(issue["body"], 300))
    if is_pull and (reviews := client.get(f"{base}/pulls/{args.number}/reviews", {"per_page": 100})):
        lines += ["Reviews:", *(f"- {r['user']['login']}: {r['state']} {_ago(r.get('submitted_at'))}"
                                + (f": {_cut(r['body'], 300)}" if r.get("body") else "") for r in reviews[-10:])]
    if issue.get("comments"):
        comments = client.get(f"{base}/issues/{args.number}/comments", {"per_page": 100})
        lines += ["Recent comments:", *(f"- {c['user']['login']} {_ago(c.get('created_at'))}: {_cut(c['body'], 300)}"
                                        for c in comments[-10:])]
    return "\n".join(lines)


def _event(event):
    p, who, kind = event.get("payload") or {}, (event.get("actor") or {}).get("login", "?"), event.get("type", "")
    url = None
    if kind == "PushEvent":
        branch = (p.get("ref") or "").removeprefix("refs/heads/")
        what = f"pushed {p['size']} commits to {branch}" if p.get("size") else f"pushed to {branch}"
    elif kind in ("PullRequestEvent", "PullRequestReviewEvent") and p.get("pull_request"):
        pull, url = p["pull_request"], p["pull_request"].get("html_url")
        action = "merged" if p.get("action") == "closed" and pull.get("merged") else p.get("action", "")
        if kind == "PullRequestReviewEvent":
            action = f"reviewed ({(p.get('review') or {}).get('state', '')})"
        what = f'{action} pull request #{pull.get("number")} "{_cut(pull.get("title"), 120)}"'
    elif kind in ("IssuesEvent", "IssueCommentEvent") and p.get("issue"):
        issue, url = p["issue"], p["issue"].get("html_url")
        action = "commented on" if kind == "IssueCommentEvent" else p.get("action", "")
        what = f'{action} issue #{issue.get("number")} "{_cut(issue.get("title"), 120)}"'
    elif kind == "ReleaseEvent" and p.get("release"):
        what, url = f"published release {p['release'].get('tag_name')}", p["release"].get("html_url")
    elif kind in ("CreateEvent", "DeleteEvent"):
        what = f"{'created' if kind == 'CreateEvent' else 'deleted'} {p.get('ref_type', '')} {p.get('ref') or ''}".strip()
    else:
        what = kind.removesuffix("Event").lower() or "did something"
    return f"{_ago(event.get('created_at'))} · {who} {what}" + (f" · {url}" if url else "")


def _repo_activity(client, args):
    repo = _full(client, args.repo)
    events = client.get(f"/repos/{repo}/events", {"per_page": 30})
    if not events:
        return f"No recent activity in {repo}."
    return "\n".join([f"Recent activity in {repo}, newest first:", *map(_event, events)])


def _repositories(client, args):
    repos, total = repositories(client)
    if not repos:
        return ("The app can't see any repository yet: the user can add some from the Connected accounts page of "
                "their Indico profile.")
    listed = f" (the first {len(repos)} listed)" if total > len(repos) else ""
    return "\n".join([f"The app can see {total} repositories{listed}:", *(
        r["full_name"] + (" (private)" if r.get("private") else "")
        + (f" · {_cut(r['description'], 100)}" if r.get("description") else "") + f" · {r['html_url']}"
        for r in repos)])


TOOLS = (
    Tool("my_pull_requests", MyPullRequestsArgs, _my_pull_requests),
    Tool("review_requests", ReviewRequestsArgs, _review_requests),
    Tool("my_issues", MyIssuesArgs, _my_issues),
    Tool("search", SearchArgs, _search_tool),
    Tool("item", ItemArgs, _item),
    Tool("repo_activity", ActivityArgs, _repo_activity),
    Tool("repositories", RepositoriesArgs, _repositories),
)
