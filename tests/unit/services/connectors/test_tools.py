"""The seven read tools (spec 023 FR-015, T020), against the fake GitHub: what each asks, and what it returns."""

import re

import pytest
from pydantic import ValidationError

from indico_assistant.services.connectors import github
from indico_assistant.services.connectors.fake_github import FakeGitHub
from indico_assistant.services.connectors.github import TOOLS, GitHubClient, GitHubError, OAuthApp


@pytest.fixture
def fake(tmp_path):
    return FakeGitHub(tmp_path / "fake.json")


@pytest.fixture
def client(fake):
    tokens = OAuthApp("Iv1.fake", "fake-secret", transport=fake.transport()).exchange("fake-code", "v", "https://cb")
    return GitHubClient(tokens.access, transport=fake.transport())


def run(client, name, **arguments):
    """(text, urls): what the tool returns."""
    (tool,) = [t for t in TOOLS if t.name == name]
    return tool.run(client, tool.args(tool=name, **arguments))


def call(client, name, **arguments):
    return run(client, name, **arguments)[0]


def numbers(text):
    return sorted(int(n) for n in re.findall(r"^#(\d+) ", text, re.M))


def test_there_are_seven_tools_each_described_with_a_literal_name():
    assert [t.name for t in TOOLS] == ["my_pull_requests", "review_requests", "my_issues", "search", "item",
                                       "repo_activity", "repositories"]
    for tool in TOOLS:
        assert tool.description and tool.args.model_fields["tool"].annotation.__args__ == (tool.name,)


def test_my_open_pull_requests(client, fake):
    text = call(client, "my_pull_requests")
    assert numbers(text) == [16, 17, 30] and "is:pr author:@me is:open" in fake.searches[-3:]
    assert "https://github.com/thoth-labs/indico-assistant/pull/16" in text and "(draft)" in text  # (#17)


@pytest.mark.parametrize(("state", "expected", "query"), [
    ("merged", [12], "is:pr author:@me is:merged"),
    ("closed", [28], "is:pr author:@me is:closed is:unmerged"),
    ("all", [12, 16, 17, 28, 30], "is:pr author:@me"),
])
def test_my_pull_requests_by_state(client, fake, state, expected, query):
    assert numbers(call(client, "my_pull_requests", state=state)) == expected and fake.searches[-1] == query


def test_one_repository_only(client, fake):
    assert numbers(call(client, "my_pull_requests", repo="thoth-labs/ibis-routing")) == [30]
    assert "is:pr author:@me is:open repo:thoth-labs/ibis-routing" in fake.searches[-3:]


def test_reviews_waiting_on_me(client, fake):
    assert numbers(call(client, "review_requests")) == [15, 18, 31]
    assert fake.searches[-1] == "is:pr is:open review-requested:@me"


def test_my_issues(client, fake):
    assert numbers(call(client, "my_issues")) == [8, 20, 40] and fake.searches[-1] == "is:issue assignee:@me is:open"
    assert numbers(call(client, "my_issues", state="closed")) == [5]
    assert numbers(call(client, "my_issues", repo="thoth-labs/ibis-routing")) == [40]


def test_search_asks_for_one_kind(client, fake):
    assert numbers(call(client, "search", kind="issue", query="today")) == [8]
    assert fake.searches[-1] == "is:issue today"
    assert numbers(call(client, "search", kind="pull_request", query="router")) == [15]
    assert fake.searches[-1] == "is:pr router"


def test_nothing_found_says_so(client):
    assert "No " in call(client, "search", kind="issue", query="no-such-word")


def test_a_pull_request_in_full(client):
    text = call(client, "item", repo="thoth-labs/indico-assistant", number=16)
    assert "Issue reports from the chat" in text and "open" in text
    assert "makoto-k: CHANGES_REQUESTED" in text and "Please split the migration" in text  # (the reviews)
    assert "The form looks good on desktop." in text  # (the comments)


def test_an_issue_has_no_reviews(client, fake):
    text = call(client, "item", repo="thoth-labs/indico-assistant", number=8)
    assert "It uses UTC" in text and "Reviews" not in text
    assert not any("/pulls/" in path for _, path in fake.calls)


def test_a_repository_the_app_cant_see_raises(client):
    with pytest.raises(GitHubError) as error:
        call(client, "item", repo="thoth-labs/secret-infra", number=3)
    assert error.value.status == 404


def test_a_repositorys_recent_activity(client):
    text = call(client, "repo_activity", repo="thoth-labs/indico-assistant")
    assert "opened pull request #17" in text and "v0.9.0" in text and "pushed 4 commits" in text
    assert "https://github.com/thoth-labs/indico-assistant/pull/17" in text


def test_the_repositories_it_can_see(client):
    text = call(client, "repositories")
    assert "thoth-labs/indico-assistant" in text and "octo-dev/dotfiles" in text and "secret-infra" not in text


@pytest.mark.parametrize("repo", ["../user", "thoth-labs/..", "a/b/c", "a b/c", "..", ".", "./x", ""])
def test_a_repository_name_cant_reach_another_endpoint(repo):
    with pytest.raises(ValidationError):
        github.ActivityArgs(tool="repo_activity", repo=repo)


def test_long_text_is_cut():
    cut = github._cut("word " * 200, 300)
    assert len(cut) <= 301 and cut.endswith("…")
    assert github._cut("a\n\n  b", 300) == "a b"



# --- live run 1: a repository named without its owner ------------------------------------------------------

def test_a_bare_repository_name_is_one_of_the_users_repositories(client, fake):
    assert numbers(call(client, "my_issues", repo="ibis-routing")) == [40]
    assert fake.searches[-1] == "is:issue assignee:@me is:open repo:thoth-labs/ibis-routing"
    assert "Issue reports from the chat" in call(client, "item", repo="indico-assistant", number=16)
    assert "Recent activity in thoth-labs/ibis-routing" in call(client, "repo_activity", repo="IBIS-routing")


def test_a_bare_name_the_app_cant_see_says_which_it_can(client):
    with pytest.raises(GitHubError) as error:
        call(client, "item", repo="secret-infra", number=3)
    assert error.value.status == 404 and "thoth-labs/indico-assistant" in error.value.message


# --- Copilot's review of PR #17 ----------------------------------------------------------------------------

def test_only_the_api_fields_give_addresses(client):
    text, urls = run(client, "my_pull_requests")
    assert urls == ["https://github.com/thoth-labs/indico-assistant/pull/17",
                    "https://github.com/thoth-labs/indico-assistant/pull/16",
                    "https://github.com/thoth-labs/ibis-routing/pull/30"]
    text, urls = run(client, "item", repo="thoth-labs/indico-assistant", number=21)  # (its body links elsewhere)
    assert urls == ["https://github.com/thoth-labs/indico-assistant/issues/21"] and "evil.example" in text


def test_my_open_pull_requests_carry_their_review_decision(client, fake):
    text = call(client, "my_pull_requests")
    lines = {int(n): line for n, line in re.findall(r"^#(\d+) (.*)$", text, re.M)}
    assert "changes requested" in lines[16] and "approved" in lines[30] and "no review decision yet" in lines[17]
    assert set(fake.searches[-3:]) == {"is:pr author:@me is:open", "is:pr author:@me is:open review:approved",
                                       "is:pr author:@me is:open review:changes_requested"}
    assert "review decision" not in call(client, "my_pull_requests", state="merged")


def test_a_list_reads_further_pages(client, fake):
    assert "No more pull requests opened by the user (page 2)." == call(client, "my_pull_requests", page=2)
    with pytest.raises(ValidationError):
        github.MyIssuesArgs(tool="my_issues", page=11)


def test_newest_reads_the_last_page_of_a_long_list():
    import httpx

    pages = {1: [{"n": i} for i in range(100)], 2: [{"n": i} for i in range(100, 200)], 3: [{"n": i} for i in (200, 201)]}

    def handle(request):
        page = int(request.url.params.get("page", 1))
        headers = {"link": '<https://api.github.com/x?per_page=100&page=3>; rel="last"'} if page == 1 else {}
        return httpx.Response(200, json=pages[page], headers=headers)

    newest = GitHubClient("t", transport=httpx.MockTransport(handle)).newest("/x")
    assert [i["n"] for i in newest] == list(range(192, 202))  # (the last 10 of 202, not 90-99 of the first page)


# --- the independent review of PR #17 ---------------------------------------------------------------------

def test_a_bare_name_resolves_past_the_first_100_repositories_once_per_answer():
    import httpx

    seen = []

    def handle(request):
        seen.append(request.url.path)
        if request.url.path == "/user/installations":
            return httpx.Response(200, json={"installations": [{"id": 1}]})
        page = int(request.url.params.get("page", 1))
        names = [f"o/r{i}" for i in range(100)] if page == 1 else ["o/target"]
        return httpx.Response(200, json={"total_count": 101, "repositories": [{"full_name": n} for n in names]})

    client = GitHubClient("t", transport=httpx.MockTransport(handle))
    assert github._full(client, "target") == "o/target"
    calls = len(seen)
    assert github._full(client, "r7") == "o/r7" and len(seen) == calls  # (cached for the answer)


def test_no_review_searches_without_pull_requests(client, fake):
    call(client, "my_pull_requests", page=2)
    assert not any("review:" in q for q in fake.searches)
