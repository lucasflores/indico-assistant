"""The fake GitHub (spec 023, T005): GitHub's REST and OAuth endpoints over a fixed seed, as an httpx transport, so
the real client runs against it in the tests and in dev mode."""

import pytest

from indico_assistant.services.connectors.fake_github import USER, FakeGitHub
from indico_assistant.services.connectors.github import GitHubClient, GitHubError, OAuthApp


@pytest.fixture
def fake(tmp_path):
    return FakeGitHub(tmp_path / "fake.json")


def connect(fake):
    return OAuthApp("Iv1.fake", "fake-secret", transport=fake.transport()).exchange("fake-code", "v", "https://cb")


def gh(fake, token=None):
    return GitHubClient(token or connect(fake).access, transport=fake.transport())


def search(fake, q):
    return [(item["repository_url"].split("/repos/")[1], item["number"])
            for item in gh(fake).get("/search/issues", {"q": q})["items"]]


def test_connecting_gives_a_token_pair_for_the_seed_user(fake):
    tokens = connect(fake)
    assert tokens.access.startswith("ghu_") and tokens.refresh.startswith("ghr_") and tokens.access_expires_at
    assert gh(fake, tokens.access).get("/user")["login"] == USER


def test_an_unknown_token_is_refused(fake):
    with pytest.raises(GitHubError) as error:
        gh(fake, "ghu_nobody").get("/user")
    assert error.value.status == 401


def test_search_finds_my_open_pull_requests_and_needs_one_kind(fake):
    mine = search(fake, "is:pr is:open author:@me")
    assert mine and all(repo != "thoth-labs/secret-infra" for repo, _ in mine)
    assert ("thoth-labs/indico-assistant", 16) in mine and ("thoth-labs/indico-assistant", 12) not in mine  # merged
    assert ("thoth-labs/indico-assistant", 12) in search(fake, "is:pr is:merged author:@me")
    assert search(fake, "is:pr is:open review-requested:@me")
    assert all(repo == "thoth-labs/ibis-routing" for repo, _ in search(fake, "is:issue assignee:@me repo:thoth-labs/ibis-routing"))
    with pytest.raises(GitHubError) as error:  # (app tokens can't search issues and pull requests together)
        search(fake, "author:@me")
    assert error.value.status == 422


def test_an_item_its_comments_and_a_pull_requests_reviews(fake):
    client = gh(fake)
    issue = client.get("/repos/thoth-labs/indico-assistant/issues/16")
    assert issue["pull_request"] and issue["html_url"].endswith("/pull/16")
    assert client.get("/repos/thoth-labs/indico-assistant/pulls/16")["merged"] is False
    assert client.get("/repos/thoth-labs/indico-assistant/pulls/16/reviews")
    assert isinstance(client.get("/repos/thoth-labs/indico-assistant/issues/8/comments"), list)
    assert client.get("/repos/thoth-labs/indico-assistant/events")


def test_a_repository_the_app_isnt_installed_on_is_not_found(fake):
    with pytest.raises(GitHubError) as error:
        gh(fake).get("/repos/thoth-labs/secret-infra/issues/1")
    assert error.value.status == 404


def test_the_installations_list_the_repositories_the_app_can_see(fake):
    client = gh(fake)
    (installation, *_) = client.get("/user/installations")["installations"]
    names = [r["full_name"] for r in client.get(f"/user/installations/{installation['id']}/repositories")["repositories"]]
    assert "thoth-labs/indico-assistant" in names and "thoth-labs/secret-infra" not in names


def test_a_refresh_replaces_both_tokens_once(fake):
    app = OAuthApp("Iv1.fake", "fake-secret", transport=fake.transport())
    old = connect(fake)
    new = app.refresh(old.refresh)
    assert gh(fake, new.access).get("/user")["login"] == USER
    for token in (old.access,):
        with pytest.raises(GitHubError):
            gh(fake, token).get("/user")
    with pytest.raises(GitHubError, match="bad_refresh_token"):  # single-use, as GitHub's are
        app.refresh(old.refresh)


def test_the_test_helpers(fake):
    tokens = connect(fake)
    fake.fail_next("/search/issues", 503)
    with pytest.raises(GitHubError) as error:
        search(fake, "is:pr author:@me")
    assert error.value.status == 503
    assert search(fake, "is:pr author:@me")  # (once)
    fake.expire(tokens.access)
    with pytest.raises(GitHubError):
        gh(fake, tokens.access).get("/user")
    fake.refuse_refresh()
    with pytest.raises(GitHubError, match="bad_refresh_token"):
        OAuthApp("Iv1.fake", "fake-secret", transport=fake.transport()).refresh(tokens.refresh)


def test_its_state_is_shared_through_the_file(tmp_path):
    path = tmp_path / "fake.json"
    token = connect(FakeGitHub(path)).access  # (the web server connects; the worker reads, in another process)
    assert gh(FakeGitHub(path), token).get("/user")["login"] == USER


def test_revoking_the_grant_drops_the_tokens(fake):
    tokens = connect(fake)
    OAuthApp("Iv1.fake", "fake-secret", transport=fake.transport()).revoke(tokens.access)
    with pytest.raises(GitHubError):
        gh(fake, tokens.access).get("/user")



def test_a_search_naming_what_the_token_cant_see_is_refused(fake):
    """As GitHub's search does (422), so the model hears it can't see a repository rather than "none found"."""
    for q in ("is:issue repo:thoth-labs/secret-infra", "is:pr author:rita", "is:pr review-requested:nobody"):
        with pytest.raises(GitHubError) as error:
            search(fake, q)
        assert error.value.status == 422 and "cannot be searched" in error.value.message
    assert search(fake, "is:pr author:rita-r") == [("thoth-labs/ibis-routing", 31)]
