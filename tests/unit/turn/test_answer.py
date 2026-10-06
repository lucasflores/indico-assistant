"""Every message goes through the turn (spec 025, T036): the plan shortcuts, Jev's fast path, else the agent."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from indico_assistant.services.chat.service import ChatService
from indico_assistant.services.knowledge.answer import KnowledgeResult
from indico_assistant.services.knowledge.gate import Decision
from indico_assistant.services.nl2sql.pipeline import OUT_OF_SCOPE_MESSAGE
from indico_assistant.services.turn import loop
from indico_assistant.services.turn.loop import TurnResult
from indico_assistant.services.turn.rules import RULES

PLAN = ("Here is the plan.", {"plan_id": "p1", "cannot_plan": False}, {"id": "p1"})
SETTINGS = {
    "fast_path_confidence": 0.8,
    "fast_path_out_of_scope": True,
    "nl2sql_enabled": True,
    "jev_api_key": "k",
    "github_enabled": False,
}


def jev(route, confidence=0.93):
    return Decision(route, None, False, "score", confidence=confidence)


@pytest.fixture
def answered():
    manager, context = MagicMock(), MagicMock()
    service = ChatService(session_manager=manager, context_builder=context)
    session_id = uuid4()
    manager.get_session.return_value = MagicMock(id=session_id, event_id=None)
    manager.add_assistant_message.return_value = MagicMock(id=uuid4())
    manager.offer_before.return_value = None
    manager.page_event_of.return_value = None
    manager.answer_id_of.return_value = None
    manager.holds_connector_answer.return_value = False
    context.build_context.return_value = [{"role": "user", "content": "hi"}]
    context.page_note.return_value = None
    s = SimpleNamespace(
        decide=MagicMock(return_value=jev("data")),
        chat=MagicMock(return_value=KnowledgeResult("Glad to help!")),
        agent=MagicMock(
            return_value=TurnResult(
                "From the thesis [p.21].", tools=[{"name": "search_documents", "ms": 9, "ok": True}]
            )
        ),
        plan=MagicMock(return_value=None),
        settings=dict(SETTINGS),
        event_settings={},
        event=None,
        manager=manager,
    )
    plugin = MagicMock()
    plugin.settings.get_all.side_effect = lambda: s.settings
    from indico_assistant.default_settings import DEFAULT_SETTINGS

    def setting(key, default=None):  # (as Indico's settings proxy: an unknown name raises)
        if key not in DEFAULT_SETTINGS:
            raise ValueError(f"invalid setting: plugin_assistant.{key}")
        return s.settings.get(key, default)

    plugin.settings.get.side_effect = setting
    plugin.event_settings.get.side_effect = lambda event, key: s.event_settings.get(key)

    def run(message="hi", waiting_plan=None, offer=None, event_id=None):
        manager.offer_before.return_value = offer
        manager.page_event_of.return_value = event_id
        with (
            patch.object(service, "_load_user", return_value=MagicMock(id=1, is_admin=False)),
            patch.object(service, "_validate_event_access"),
            patch("indico_assistant.plugin.AssistantPlugin", MagicMock(instance=plugin)),
            patch("indico_assistant.services.turn.answer.base_url_of", return_value="https://indico.test"),
            patch("indico_assistant.services.actions.executor.open_plan", return_value=waiting_plan),
            patch("indico_assistant.services.knowledge.gate.decide", s.decide),
            patch("indico_assistant.services.knowledge.chat.chat_answer", s.chat),
            patch("indico_assistant.services.turn.loop.run", s.agent),
            patch("indico_assistant.services.turn.abilities.plan", s.plan),
            patch("indico_assistant.services.turn.memory.load", return_value=[]),
            patch("indico_assistant.services.document.reader.documents", return_value=[]),
            patch("indico_assistant.services.turn.memory.usable", side_effect=lambda user, entries: entries),
            patch("indico.modules.events.Event.get", return_value=s.event),
            patch("indico_assistant.services.chat.service.db"),
            patch("indico.core.db.db"),
        ):
            result = service.answer(1, session_id, message, message_id=uuid4())
        return result, manager.add_assistant_message.call_args.args[2]

    return run, s


def test_chat_at_the_threshold_is_answered_on_the_fast_path(answered):
    run, s = answered
    s.decide.return_value = jev("chat", 0.8)
    result, metadata = run("thanks!")
    assert result.response == "Glad to help!" and metadata["route"]["route"] == "fast:chat"
    s.agent.assert_not_called()


def test_out_of_scope_is_refused_on_the_fast_path(answered):
    run, s = answered
    s.decide.return_value = jev("out_of_scope")
    result, metadata = run("Who won the match?")
    assert result.response == OUT_OF_SCOPE_MESSAGE and metadata["problem"] == "out_of_scope"
    assert metadata["route"]["route"] == "fast:out_of_scope"
    s.agent.assert_not_called()


@pytest.mark.parametrize(
    "decision", [jev("chat", 0.79), jev("data"), jev("knowledge"), jev("change"), Decision(None, None, True, "timeout")]
)
def test_anything_else_goes_to_the_agent(answered, decision):
    run, s = answered
    s.decide.return_value = decision
    result, metadata = run("What does the thesis say about pile-up?")
    assert result.response == "From the thesis [p.21]." and metadata["route"]["route"] == "agent"
    assert metadata["route"]["tools"] == ["search_documents"]
    assert metadata["route"]["jev"]["skipped"] is decision.skipped and metadata["touched"] == []


def test_out_of_scope_goes_to_the_agent_when_the_setting_is_off(answered):
    run, s = answered
    s.settings["fast_path_out_of_scope"] = False
    s.decide.return_value = jev("out_of_scope")
    _, metadata = run("Tell me about the Higgs boson")
    assert metadata["route"]["route"] == "agent"


def test_the_plan_shortcuts_run_before_the_turn(answered):
    run, s = answered
    s.plan.return_value = PLAN
    waiting = MagicMock(questions=[], suggestions=[], draft={})
    result, metadata = run("yes", waiting_plan=waiting)
    assert result.plan == {"id": "p1"} and metadata["route"]["route"] == "change" and metadata["route"]["shortcut"]
    s.decide.assert_not_called() and s.agent.assert_not_called()
    result, metadata = run("yes", offer="move Budget to 3pm")
    assert s.plan.call_args.args[6] == "move Budget to 3pm" and metadata["route"]["shortcut"]


def test_a_plain_no_to_an_offer_never_reaches_the_waiting_plan(answered):
    run, s = answered
    s.decide.return_value = jev("data")
    run("no", waiting_plan=MagicMock(questions=[], suggestions=[], draft={}), offer="add a reminder")
    s.plan.assert_not_called()  # (the plan's own "no" shortcut would cancel it)
    assert s.agent.call_args.args[0].waiting_plan is None


def test_an_event_with_the_assistant_off_gets_the_disabled_answer(answered):
    run, s = answered
    s.event, s.event_settings = MagicMock(id=5), {"enabled": "false"}
    result, metadata = run("hello", event_id=5)
    assert result.response == "The assistant is turned off for this event." and metadata["route"]["route"] == "disabled"
    s.decide.assert_not_called() and s.agent.assert_not_called()


def test_the_events_own_settings_reach_the_agent(answered):
    run, s = answered
    s.event = MagicMock(id=5)
    s.event_settings = {
        "enabled": "",
        "custom_system_prompt": "Answer in French.",
        "nl2sql_enabled": "false",
        "allowed_tables": "events.events, events.contributions",
    }
    run("Quels exposés?", event_id=5)
    ctx, _, tools = s.agent.call_args.args
    assert s.agent.call_args.kwargs["system_prompt"].endswith("Answer in French.")
    assert "query_data" not in [t.name for t in tools]
    assert ctx.allowed_tables == ["events.events", "events.contributions"]
    s.event_settings["nl2sql_enabled"] = ""
    run("Which talks?", event_id=5)
    assert "query_data" in [t.name for t in s.agent.call_args.args[2]]


def test_github_is_offered_only_while_it_is_on_and_connected(answered):
    run, s = answered
    run("my PRs?")
    assert "github_my_pull_requests" not in [t.name for t in s.agent.call_args.args[2]]
    s.settings["github_enabled"] = True
    with patch("indico_assistant.services.turn.abilities.github_note", return_value="GitHub: not connected"):
        run("my PRs?")
    assert "github_my_pull_requests" not in [t.name for t in s.agent.call_args.args[2]]
    assert s.agent.call_args.args[0].github_note == "GitHub: not connected"
    with patch("indico_assistant.services.turn.abilities.github_note", return_value=None):
        run("my PRs?")
    assert "github_my_pull_requests" in [t.name for t in s.agent.call_args.args[2]]


def test_a_provider_outage_on_the_fast_path_or_in_the_loop_is_a_clear_message(answered):
    run, s = answered
    s.agent.return_value = TurnResult(loop.UNAVAILABLE, stop="unavailable", failed=True)
    result, metadata = run("What is on today?")
    assert result.response == loop.UNAVAILABLE and metadata["problem"] == "failed"
    s.decide.return_value = jev("chat")
    s.chat.return_value = KnowledgeResult("I could not answer that just now.", failed=True)
    result, metadata = run("thanks")
    assert metadata["problem"] == "failed"


def test_the_answer_keeps_its_links_only_when_a_tool_or_the_conversation_gave_them(answered):
    run, s = answered
    s.agent.return_value = TurnResult("See [the page](https://indico.test/event/5/) and [evil](https://evil.test/x).")
    result, _ = run("where?")
    assert "https://evil.test" not in result.response


def _in_a_turn(run, **kwargs):
    from indico_assistant.services.analytics import recorder

    turn = recorder._Turn(1, text_on=True)
    token = recorder._current.set(turn)
    try:
        with recorder.step("jev", "route") as step:  # (Jev's text, collected before anything reads GitHub)
            recorder.text(step, "prompt", "which of my PRs are open?")
        run(**kwargs)
    finally:
        recorder._current.reset(token)
    return turn


def test_a_turn_that_reads_github_keeps_no_text_not_even_jevs(answered):
    from indico_assistant.services.analytics import recorder

    run, s = answered

    def reads_github(ctx, message, tools, system_prompt, **kwargs):
        ctx.private = True
        recorder.private()
        return TurnResult("Open: #16")

    s.agent.side_effect = reads_github
    turn = _in_a_turn(run, message="which of my PRs are open?")
    assert turn.private is True and turn.texts == {}
    assert s.manager.add_assistant_message.call_args.args[2]["route"]["private"] is True


def test_a_chat_that_holds_a_github_answer_keeps_no_text(answered):
    run, s = answered
    s.manager.holds_connector_answer.return_value = True
    assert _in_a_turn(run, message="and how do I lock an event?").private is True


def test_other_turns_keep_their_text(answered):
    run, _ = answered
    turn = _in_a_turn(run)
    assert turn.private is False and list(turn.texts) == [(1, "prompt")]


def test_the_answer_is_linked_to_its_turn_before_the_answer_is_committed(answered):
    """Review of #21 (FR-007): in the answer's own transaction, so a vote always finds its turn."""
    from indico_assistant.services.analytics import recorder

    run, s = answered
    seen = {}
    s.manager.commit.side_effect = lambda: seen.setdefault("at_commit", dict(turn.fields))
    turn = recorder._Turn(1, text_on=True)
    token = recorder._current.set(turn)
    try:
        run()
    finally:
        recorder._current.reset(token)
    assert seen["at_commit"]["answer_id"] == s.manager.add_assistant_message.return_value.id


@pytest.mark.parametrize(
    "message",
    ["thanks", "What does the thesis say?", "Move it to 3pm", "how do I lock it?", "my PRs?", "Who won the match?"],
)
def test_every_answer_goes_through_the_turn_unless_a_plan_shortcut_takes_it(answered, message):
    """SC-009 (story 2's half): no other way to an answer is left in the chat service."""
    run, s = answered
    with patch("indico_assistant.services.turn.answer.answer", wraps=None) as turn:
        turn.return_value = __import__("indico_assistant.services.turn.answer", fromlist=["Outcome"]).Outcome(
            "ok", {}, "agent"
        )
        run(message)
    turn.assert_called_once()
    for old in ("_process_with_nl2sql", "_knowledge", "_chat", "_connector", "_decide", "_plan"):
        assert not hasattr(ChatService, old)


def test_an_event_page_without_its_own_settings_inherits_the_global_ones(answered):
    """Seen live (quick run 1): allowed_tables and custom_system_prompt have no global setting to fall back to."""
    run, s = answered
    s.event, s.event_settings = MagicMock(id=5), {}
    result, metadata = run("Which talks are on today?", event_id=5)
    assert metadata["route"]["route"] == "agent"
    ctx, _, tools = s.agent.call_args.args
    assert ctx.allowed_tables is None and "query_data" in [t.name for t in tools]
    assert s.agent.call_args.kwargs["system_prompt"] == RULES  # (no event prompt appended)


def test_documents_in_play_require_a_first_lookup(answered):
    run, s = answered
    run("What is the weather like?")
    assert s.agent.call_args.kwargs["lookup_first"] is False
    run("What does the thesis say about pile-up?")
    assert s.agent.call_args.kwargs["lookup_first"] is True


def test_the_answers_order_numbers_the_documents():
    from indico_assistant.services.turn.answer import in_presented_order

    touched = [
        {"kind": "document", "ref": {"attachment_id": a}, "title": f"d{a}", "position": n}
        for n, a in enumerate([4, 9, 7], 1)
    ] + [{"kind": "event", "ref": {"event_id": 1}, "title": "E", "position": 1}]
    ordered = in_presented_order(touched, [7, 4])
    assert [(e["ref"].get("attachment_id"), e["position"]) for e in ordered] == [(7, 1), (4, 2), (9, 3), (None, 1)]
