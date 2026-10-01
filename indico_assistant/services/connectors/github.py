"""GitHub, read with the user's own token (spec 023): the client, the app's OAuth calls, and the read tools.

The token only ever travels in a header (FR-009): never in a URL, and never in an error's message. The OAuth calls
send their secrets in the request body, not the query string.
"""

import os
import re
import time
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


def _json(response):
    """The body, or a GitHubError (502: treated as GitHub being unreachable) when it isn't JSON (a proxy's page)."""
    try:
        return response.json()
    except ValueError:
        raise GitHubError(502, "GitHub's answer wasn't JSON") from None


def _last_page(link):
    """The last page's number in GitHub's ``Link`` header, or None."""
    found = re.search(r'[?&]page=(\d+)[^>]*>; rel="last"', link or "")
    return int(found.group(1)) if found else None


class GitHubClient:
    """GitHub's REST API as one user. One per answer: ``with GitHubClient(...) as client``."""

    def __init__(self, token, *, timeout=10, transport=None):
        self._http = httpx.Client(base_url=API, timeout=timeout, transport=transport, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION})
        self._timeout = timeout
        self.cache = {}  # (for one answer: e.g. the repositories, once however many bare names it resolves)
        #: (time.monotonic) no call starts after it, and none outlasts it: the loop's whole budget, however many calls
        #: one tool makes (fresh-review)
        self.deadline = None

    def _get(self, path, params=None):
        if self.deadline is None:
            return _send(self._http, "GET", path, params=params)
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise GitHubError(0, "GitHub took too long for this answer")
        return _send(self._http, "GET", path, params=params, timeout=min(self._timeout, left))

    def get(self, path, params=None):
        return _json(self._get(path, params))

    def newest(self, path, n=10):
        """The newest ``n`` of a list GitHub returns oldest first, a page of 100 at a time: from its last page (and
        the one before, when that is short), not from the first page (Copilot, PR #17)."""
        first = self._get(path, {"per_page": 100})
        items, last = _json(first), _last_page(first.headers.get("link"))
        if last and last > 1:
            before = items  # (page 1: when it is the page before the last, it is reused, not fetched again)
            items = self.get(path, {"per_page": 100, "page": last})
            if len(items) < n:
                items = (before if last == 2 else self.get(path, {"per_page": 100, "page": last - 1})) + items
        return items[-n:]

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
            body = _json(_send(http, "POST", f"{WEB}/login/oauth/access_token", headers={"Accept": "application/json"},
                               data={"client_id": self.client_id, "client_secret": self._secret, **fields}))
        if not isinstance(body, dict):
            raise GitHubError(502, "GitHub's answer wasn't a token")
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
    ``limit``, and how many there are in all. Each installation's list is read a page of 100 at a time until
    ``limit``."""
    found, total = [], 0
    # ponytail: the first 100 installations only; a user reaching more is not a case yet
    for installation in client.get("/user/installations", {"per_page": 100})["installations"]:
        for page in range(1, limit // 100 + 2):
            batch = client.get(f"/user/installations/{installation['id']}/repositories",
                               {"per_page": 100, "page": page})
            total += batch["total_count"] if page == 1 else 0
            if len(found) < limit:
                found += batch["repositories"]
            if len(found) >= limit or len(batch["repositories"]) < 100:
                break
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
    if "repositories" not in client.cache:  # (fresh-review: once per answer, and past the first 100)
        client.cache["repositories"] = [r["full_name"] for r in repositories(client, limit=1000)[0]]
    names = client.cache["repositories"]
    found = [name for name in names if name.split("/")[1].lower() == repo.lower()]
    if len(found) == 1:
        return found[0]
    raise GitHubError(404, f"{repo} could be any of: {', '.join(found)}" if found else
                      f"no repository named {repo} that the app can see (it sees: {', '.join(names) or 'none'})")


#: Which page of a list (20 each): a list beyond 20 items is read a page at a time (Copilot, PR #17).
Page = Annotated[int, Field(ge=1, le=10, description="Which page of 20 results, for more; 1 is the newest")]


class MyPullRequestsArgs(BaseModel):
    """Pull requests the user opened: open by default (with each one's review decision), or closed (not merged),
    merged, or all."""
    tool: Literal["my_pull_requests"]
    state: Literal["open", "closed", "merged", "all"] = "open"
    repo: Repo | None = None
    page: Page = 1


class ReviewRequestsArgs(BaseModel):
    """Open pull requests waiting for the user's review."""
    tool: Literal["review_requests"]
    page: Page = 1


class MyIssuesArgs(BaseModel):
    """Issues assigned to the user: open by default, or closed, or all."""
    tool: Literal["my_issues"]
    state: Literal["open", "closed", "all"] = "open"
    repo: Repo | None = None
    page: Page = 1


class SearchArgs(BaseModel):
    """Issues or pull requests (one kind per call) matching a GitHub search, e.g. "involves:@me timezone" or
    "repo:owner/name label:bug"."""
    tool: Literal["search"]
    kind: Literal["issue", "pull_request"]
    query: str = Field(..., max_length=200)
    page: Page = 1


class ItemArgs(BaseModel):
    """One issue or pull request in full: its state, labels, description, its newest comments and, for a pull
    request, its newest reviews."""
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


def _login(user):
    """A user's login; GitHub gives ``null`` for a deleted account (fresh-review)."""
    return (user or {}).get("login") or "ghost"


def _where(item):
    return item["repository_url"].split("/repos/", 1)[1], item["number"]


def _line(item, note=None):
    """One issue or pull request from a search or an item, on one line, with its own address."""
    pull = item.get("pull_request")
    state = "merged" if pull and pull.get("merged_at") else item.get("state", "?")
    repo, number = _where(item)
    bits = [f"#{number} {repo}", f'"{_cut(item.get("title"), 120)}"', state + (" (draft)" if item.get("draft") else ""),
            f"opened {_ago(item.get('created_at'))} by {_login(item.get('user'))}"]
    if note:
        bits.append(note)
    if item.get("labels"):
        bits.append("labels: " + ", ".join(label["name"] for label in item["labels"]))
    if item.get("comments"):
        bits.append(f"{item['comments']} comments")
    return " · ".join(bits) + f" · {item['html_url']}"


def _find(client, q, page=1, per_page=20):
    data = client.get("/search/issues", {"q": q, "per_page": per_page, "page": page, "sort": "created",
                                         "order": "desc"})
    return data.get("items") or [], data.get("total_count", 0)


def _listing(items, total, page, what, notes=None):
    """(text, the items' own addresses): only these, from the API's fields, may be linked (Copilot, PR #17)."""
    if not items:
        return (f"No {what} found." if page == 1 else f"No more {what} (page {page})."), []
    first = (page - 1) * 20 + 1
    more = total > first + len(items) - 1
    hint = f"; ask for page {page + 1} for more" if page < 10 else "; a list reads no further than page 10"
    shown = f" (showing {first}-{first + len(items) - 1}{hint})" if more else ""
    lines = [_line(item, (notes or {}).get(_where(item))) for item in items]
    return "\n".join([f"{total} {what}{shown}:", *lines]), [item["html_url"] for item in items]


def _search(client, q, what, page=1, notes=None):
    items, total = _find(client, q, page)
    return _listing(items, total, page, what, notes(items) if notes else None)


def _query(*parts):
    return " ".join(p for p in parts if p)


def _decisions(client, q, page=1):
    """Each open pull request's review decision, from two more searches (a search result carries none), reading as
    many pages of 100 as reach the listed page (fresh-review: two, for page 6 to 10)."""
    pages = -(-page * 20 // 100)

    def found(qualifier):
        return {_where(item) for k in range(1, pages + 1)
                for item in _find(client, f"{q} {qualifier}", page=k, per_page=100)[0]}

    def notes(items):  # (only when the list has items: GitHub allows 30 searches a minute)
        if not items:
            return {}
        approved, changes = found("review:approved"), found("review:changes_requested")
        return {_where(i): ("changes requested" if _where(i) in changes else "approved" if _where(i) in approved
                            else "no review decision yet") for i in items}

    return notes


def _my_pull_requests(client, args):
    state = {"open": "is:open", "closed": "is:closed is:unmerged", "merged": "is:merged", "all": ""}[args.state]
    repo = _full(client, args.repo)
    q = _query("is:pr author:@me", state, repo and f"repo:{repo}")
    return _search(client, q, "pull requests opened by the user", args.page,
                   _decisions(client, q, args.page) if args.state == "open" else None)


def _review_requests(client, args):
    return _search(client, "is:pr is:open review-requested:@me", "open pull requests waiting for the user's review",
                   args.page)


def _my_issues(client, args):
    state = {"open": "is:open", "closed": "is:closed", "all": ""}[args.state]
    repo = _full(client, args.repo)
    return _search(client, _query("is:issue assignee:@me", state, repo and f"repo:{repo}"),
                   "issues assigned to the user", args.page)


def _search_tool(client, args):
    kind = "is:pr" if args.kind == "pull_request" else "is:issue"
    return _search(client, f"{kind} {args.query}", "pull requests" if args.kind == "pull_request" else "issues",
                   args.page)


def _item(client, args):
    base = f"/repos/{_full(client, args.repo)}"
    issue = client.get(f"{base}/issues/{args.number}")
    is_pull = bool(issue.get("pull_request"))
    lines = [_line(issue)]
    if is_pull:
        pull = client.get(f"{base}/pulls/{args.number}")
        asked = ", ".join(_login(r) for r in pull.get("requested_reviewers") or [])
        lines.append(f"From {pull['head']['ref']} into {pull['base']['ref']}"
                     + (f"; review requested from {asked}" if asked else ""))
    if issue.get("assignees"):
        lines.append("Assigned to " + ", ".join(_login(a) for a in issue["assignees"]))
    if issue.get("body"):
        lines.append("Description: " + _cut(issue["body"], 300))
    if is_pull and (reviews := client.newest(f"{base}/pulls/{args.number}/reviews")):
        lines += ["Newest reviews:", *(f"- {_login(r.get('user'))}: {r['state']} {_ago(r.get('submitted_at'))}"
                                       + (f": {_cut(r['body'], 300)}" if r.get("body") else "") for r in reviews)]
    if issue.get("comments"):
        comments = client.newest(f"{base}/issues/{args.number}/comments")
        lines += ["Newest comments:", *(f"- {_login(c.get('user'))} {_ago(c.get('created_at'))}: {_cut(c['body'], 300)}"
                                        for c in comments)]
    return "\n".join(lines), [issue["html_url"]]


def _event(event):
    """One event on one line, and its address from the API's own fields (or None)."""
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
    return f"{_ago(event.get('created_at'))} · {who} {what}" + (f" · {url}" if url else ""), url


def _repo_activity(client, args):
    repo = _full(client, args.repo)
    events = [_event(e) for e in client.get(f"/repos/{repo}/events", {"per_page": 30})]
    if not events:
        return f"No recent activity in {repo}.", []
    return ("\n".join([f"Recent activity in {repo}, newest first:", *(line for line, _ in events)]),
            [url for _, url in events if url])


def _repositories(client, args):
    repos, total = repositories(client)
    if not repos:
        return ("The app can't see any repository yet: the user can add some from the Connected accounts page of "
                "their Indico profile."), []
    listed = f" (the first {len(repos)} listed)" if total > len(repos) else ""
    return "\n".join([f"The app can see {total} repositories{listed}:", *(
        r["full_name"] + (" (private)" if r.get("private") else "")
        + (f" · {_cut(r['description'], 100)}" if r.get("description") else "") + f" · {r['html_url']}"
        for r in repos)]), [r["html_url"] for r in repos]


TOOLS = (
    Tool("my_pull_requests", MyPullRequestsArgs, _my_pull_requests),
    Tool("review_requests", ReviewRequestsArgs, _review_requests),
    Tool("my_issues", MyIssuesArgs, _my_issues),
    Tool("search", SearchArgs, _search_tool),
    Tool("item", ItemArgs, _item),
    Tool("repo_activity", ActivityArgs, _repo_activity),
    Tool("repositories", RepositoriesArgs, _repositories),
)
