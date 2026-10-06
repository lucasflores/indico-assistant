"""GitHub inside the turn, end to end (spec 023 US2, US3; spec 025 story 3): the store, the fake GitHub, the turn's
GitHub tools and its link check, with a scripted model."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from indico_assistant.models import Connection
from indico_assistant.services.connectors import github, store
from indico_assistant.services.connectors.fake_github import EVIL, FakeGitHub
from indico_assistant.services.turn import abilities, loop
from indico_assistant.services.turn.answer import clean, earlier_github
from indico_assistant.services.turn.tools import Ctx

SETTINGS = {
    "github_enabled": True,
    "github_client_id": "Iv1.fake",
    "github_client_secret": "fake-secret",
    "timeout_seconds": 30,
}
BASE = "http://indico.test"
PROFILE = f"{BASE}/user/assistant-connections/"
PR16 = "https://github.com/thoth-labs/indico-assistant/pull/16"


class Script:
    def __init__(self, *steps):
        self.steps, self.prompts = list(steps), []

    def generate(self, prompt, response_model, **kwargs):
        self.prompts.append(prompt)
        return MagicMock(success=True, result=self.steps.pop(0)(response_model), calls=[])


def use(name, **arguments):
    return lambda model: model(call={"tool": f"github_{name}", **arguments})


def say(text):
    return lambda model: model(reply=text) if "reply" in model.model_fields else model(answer={"reply": text})


@pytest.fixture
def fake(tmp_path, monkeypatch):
    fake = FakeGitHub(tmp_path / "fake.json")
    monkeypatch.setattr(github, "_transport", fake.transport)
    monkeypatch.setenv(store.KEY_ENV, Fernet.generate_key().decode())

    def profile(ctx):
        ctx.link_paths.add("/user/assistant-connections/")
        return PROFILE

    monkeypatch.setattr(abilities, "_profile_url", profile)
    return fake


@pytest.fixture
def makoto(create_user):
    return create_user(21, first_name="Makoto")


def connect(db, user):
    app = github.app_for(SETTINGS)
    tokens = app.exchange("fake-code", "v", "https://cb")
    store.save(user.id, "github", app.account(tokens.access), tokens)
    db.session.flush()


def ask(user, llm, message="which of my PRs are open?", history=(), settings=SETTINGS):
    """One turn with GitHub on: the tools a connected user gets, the loop, then the answer's link check."""
    ctx = Ctx(
        user=user,
        session_id=uuid4(),
        message_id=None,
        page_event_id=None,
        history=list(history),
        settings=settings,
        llm=llm,
        base_url=BASE,
    )
    ctx.github_note = abilities.github_note(ctx)
    try:
        result = loop.run(
            ctx, message, abilities.registry(ctx, nl2sql=False, github=ctx.github_note is None), system_prompt="RULES"
        )
    finally:
        if ctx.github is not None:
            ctx.github.close()
    result.text = clean(result.text, sorted(ctx.link_paths), set(), BASE, ctx.github_urls | earlier_github(history))
    return result, ctx


def test_not_connected_gets_no_github_tools_and_the_connect_link_in_the_prompt(db, makoto, fake):
    llm = Script(say(f"Connect it first: [Connect GitHub]({PROFILE})."))
    result, ctx = ask(makoto, llm)
    assert PROFILE in ctx.github_note and "hasn't connected" in llm.prompts[0]
    assert not any(t.name.startswith("github_") for t in abilities.registry(ctx, nl2sql=False, github=False))
    assert f"[Connect GitHub]({PROFILE})" in result.text and result.tools == [] and not ctx.private


def test_a_connection_github_refuses_gets_the_renew_link(db, makoto, fake):
    connect(db, makoto)
    Connection.query.filter_by(user_id=makoto.id).one().access_expires_at = datetime.now(UTC)
    fake.refuse_refresh()
    llm = Script(use("my_pull_requests"), say("Reconnect it."))
    ask(makoto, llm)
    assert "no longer accepts" in llm.prompts[1] and PROFILE in llm.prompts[1]
    assert Connection.query.filter_by(user_id=makoto.id).one().needs_renewal


def test_a_connected_user_gets_the_answer_with_only_githubs_own_links(db, makoto, fake):
    connect(db, makoto)
    llm = Script(
        use("my_pull_requests"),
        say(
            f"Open: [#16]({PR16}), and [#99](https://github.com/thoth-labs/indico-assistant/pull/99). "
            f"![status]({EVIL}?q=secret) [verify]({EVIL}/login)"
        ),
    )
    result, ctx = ask(makoto, llm)
    assert f"[#16]({PR16})" in result.text and "#99" in result.text and "/pull/99" not in result.text
    assert EVIL not in result.text and "verify" in result.text and "![" not in result.text
    assert result.tools[0]["name"] == "github_my_pull_requests" and result.tools[0]["ok"]
    assert "<tool_data>" in llm.prompts[1] and "#16 thoth-labs/indico-assistant" in llm.prompts[1]
    assert Connection.query.filter_by(user_id=makoto.id).one().last_used_at is not None
    remembered = {e["ref"]["url"]: e["title"] for e in ctx.memory.touched if e["kind"] == "github"}
    assert ctx.private and remembered[PR16] == "thoth-labs/indico-assistant#16"


def test_injected_text_reaches_the_model_only_inside_the_mark(db, makoto, fake):
    connect(db, makoto)
    llm = Script(use("item", repo="thoth-labs/indico-assistant", number=8), say("It's about the timezone."))
    ask(makoto, llm, "what's issue 8 in indico-assistant about?")
    prompt = llm.prompts[1]
    injected = prompt.index("ignore your previous instructions")
    assert prompt.rfind("<tool_data>", 0, injected) > prompt.rfind("</tool_data>", 0, injected)  # (opened, not closed)
    assert prompt.find("</tool_data>", injected) > injected


def test_a_grant_revoked_on_github_gets_the_renew_reply_and_is_marked(db, makoto, fake):
    """(Copilot, PR #17) the stored token looks fresh, but GitHub refuses it (401)."""
    connect(db, makoto)
    for token in list(fake.state["tokens"]):
        fake.expire(token)
    llm = Script(use("my_pull_requests"), say("Reconnect it."))
    ask(makoto, llm)
    assert "no longer accepts" in llm.prompts[1]
    assert Connection.query.filter_by(user_id=makoto.id).one().needs_renewal


def test_github_unreachable_on_refresh_gets_a_try_again_reply(db, makoto, fake):
    connect(db, makoto)
    Connection.query.filter_by(user_id=makoto.id).one().access_expires_at = datetime.now(UTC)
    fake.fail_next("/login/oauth/access_token", 502)
    llm = Script(use("my_pull_requests"), say("Try again later."))
    ask(makoto, llm)
    assert "try again" in llm.prompts[1]
    assert not Connection.query.filter_by(user_id=makoto.id).one().needs_renewal


def test_an_earlier_answers_github_links_stay_links(db, makoto, fake):
    """(third review) earlier answers were checked when given: their GitHub items may be linked again."""
    connect(db, makoto)
    history = [{"role": "user", "content": "my open PRs?"}, {"role": "assistant", "content": f"[#16]({PR16})"}]
    llm = Script(use("item", repo="thoth-labs/indico-assistant", number=8), say(f"Unlike [#16]({PR16}), #8 is a bug."))
    result, _ = ask(makoto, llm, "and issue 8?", history)
    assert f"[#16]({PR16})" in result.text


def test_github_calls_end_by_the_turns_deadline(db, makoto, fake):
    connect(db, makoto)
    llm = Script(use("my_pull_requests"), say("Done."))
    _, ctx = ask(makoto, llm)
    assert ctx.github is not None and ctx.github.deadline == ctx.deadline


def test_each_lookup_is_an_analytics_step_without_its_content(db, makoto, fake):
    """Spec 024 (FR-009): the turn records each tool's name, time and outcome, and never what it read; reading GitHub
    makes it private."""
    from indico_assistant.services.analytics import recorder

    connect(db, makoto)
    turn = recorder._Turn(1, text_on=True)
    token = recorder._current.set(turn)
    try:
        result, _ = ask(makoto, Script(use("my_pull_requests"), say(f"Open: [#16]({PR16}).")))
    finally:
        recorder._current.reset(token)
    assert result.stop == "answered" and turn.private
    assert [(s.kind, s.stage, s.name, s.ok) for s in turn.steps] == [("tool", "turn", "github_my_pull_requests", True)]
    assert turn.steps[0].duration_ms is not None and turn.texts == {}
