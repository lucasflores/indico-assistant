"""How ChatService.answer routes a message (spec 022, Lucas 2026-09-30): the exact shortcut, one Jev decision (or
the classifier without it), the planner's fall-through to the knowledge answer, and the route record."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from indico_assistant.services.chat.service import ChatService
from indico_assistant.services.knowledge.answer import KnowledgeResult
from indico_assistant.services.knowledge.gate import Decision
from indico_assistant.services.nl2sql.pipeline import OUT_OF_SCOPE_MESSAGE

KNOWLEDGE = KnowledgeResult("Use the gear menu, then Lock.", guide_commit="e7e0016")
CHAT = KnowledgeResult("The earliest is the Sync.")
PLAN = ("Here is the plan.", {"plan_id": "p1", "cannot_plan": False}, {"id": "p1"})
CANNOT = ("I could not work out what to change.", {"plan_id": None, "cannot_plan": True}, None)


def jev(route, intent=None):
    return Decision(route, intent, False, "score", confidence=0.93)


SKIPPED = Decision(None, None, True, "no key")


@pytest.fixture
def routed():
    manager, context = MagicMock(), MagicMock()
    service = ChatService(session_manager=manager, context_builder=context)
    session_id = uuid4()
    manager.get_session.return_value = MagicMock(id=session_id, event_id=None)
    manager.add_assistant_message.return_value = MagicMock(id=uuid4())
    manager.offer_before.return_value = None
    manager.page_event_of.return_value = None
    manager.answer_id_of.return_value = None
    context.build_context.return_value = [{"role": "user", "content": "hi"}]
    context.page_note.return_value = None
    s = MagicMock()
    s.decide.return_value = SKIPPED
    s.plan.return_value = None
    s.nl2sql.return_value = ("An answer", {})
    s.knowledge.return_value = KNOWLEDGE
    s.chat.return_value = CHAT

    def run(message="hi", waiting_plan=None):
        with patch.object(service, "_load_user", return_value=MagicMock(id=1, is_admin=False)), \
                patch.object(service, "_decide", s.decide), patch.object(service, "_plan", s.plan), \
                patch.object(service, "_process_with_nl2sql", s.nl2sql), \
                patch.object(service, "_knowledge", s.knowledge), patch.object(service, "_chat", s.chat), \
                patch("indico_assistant.services.actions.executor.open_plan", return_value=waiting_plan), \
                patch("indico_assistant.services.chat.service.db"):
            result = service.answer(1, session_id, message, message_id=uuid4())
        return result, manager.add_assistant_message.call_args.args[2]["route"]
    s.manager = manager
    return run, s


def test_a_plain_yes_to_a_waiting_plan_needs_neither_jev_nor_a_model(routed):
    run, s = routed
    s.plan.return_value = PLAN
    waiting = MagicMock(questions=[], suggestions=[], draft={})
    result, route = run("yes", waiting_plan=waiting)
    assert result.plan == {"id": "p1"} and route["route"] == "change" and route["shortcut"] is True
    s.decide.assert_not_called()
    assert s.plan.call_args.args[4] is waiting


@pytest.mark.parametrize(("where", "stub"), [("knowledge", "knowledge"), ("chat", "chat")])
def test_jev_sends_it_to_an_answer(routed, where, stub):
    run, s = routed
    s.decide.return_value = jev(where)
    result, route = run("How do I lock my event?")
    assert result.response == getattr(s, stub).return_value.text and route["route"] == where
    assert route["jev"]["route"] == where and route["fallback"] is None and route["shortcut"] is False
    s.nl2sql.assert_not_called() and s.plan.assert_not_called()


def test_a_data_question_carries_its_intent_and_skips_the_classifier(routed):
    run, s = routed
    s.decide.return_value = jev("data", "speaker_query")
    result, route = run("Who speaks at Q3 planning?")
    assert result.response == "An answer" and route["route"] == "data" and route["jev"]["intent"] == "speaker_query"
    assert s.nl2sql.call_args.kwargs["intent"] == "speaker_query" and s.nl2sql.call_args.kwargs["intent_confidence"] == 0.93


def test_a_change_goes_to_the_planner_with_the_waiting_plan(routed):
    run, s = routed
    s.decide.return_value = jev("change")
    s.plan.return_value = PLAN
    waiting = MagicMock()
    result, route = run("make it 11 instead", waiting_plan=waiting)
    assert result.plan == {"id": "p1"} and route["route"] == "change"
    assert s.plan.call_args.args[4] is waiting


def test_a_change_the_planner_cannot_plan_gets_the_knowledge_answer(routed):
    run, s = routed
    s.decide.return_value = jev("change")
    s.plan.return_value = CANNOT
    result, route = run("Can you register me for this event?")
    assert result.response == KNOWLEDGE.text and route["route"] == "knowledge" and route["fallback"] == "planner"
    assert result.plan is None


def test_a_change_the_planner_calls_unrelated_gets_the_knowledge_answer(routed):
    """Run 1: "Can you upload my slides?" came back "I could not work out what to change"."""
    run, s = routed
    s.decide.return_value = jev("change")
    s.plan.return_value = None
    result, route = run("Can you upload my slides to my talk?")
    assert result.response == KNOWLEDGE.text and route["fallback"] == "planner"


def test_with_a_waiting_plan_the_planners_reply_stands(routed):
    run, s = routed
    s.decide.return_value = jev("change")
    s.plan.return_value = CANNOT
    result, route = run("hmm, make it better", waiting_plan=MagicMock())
    assert result.response == CANNOT[0] and route["route"] == "change"
    s.knowledge.assert_not_called()


def test_out_of_scope_gets_the_fixed_refusal(routed):
    run, s = routed
    s.decide.return_value = jev("out_of_scope")
    result, route = run("What's the weather in Geneva?")
    assert result.response == OUT_OF_SCOPE_MESSAGE and route["route"] == "refusal"
    s.nl2sql.assert_not_called()


@pytest.mark.parametrize(("flags", "want"), [
    ({"knowledge_request": True}, "knowledge"), ({"chat_request": True}, "chat"), ({}, "data"),
    ({"pipeline_error": {"error_type": "out_of_scope"}}, "refusal"),
])
def test_without_jev_the_classifier_routes(routed, flags, want):
    run, s = routed
    s.nl2sql.return_value = ("An answer", flags)
    _, route = run("a question")
    assert route["route"] == want and route["fallback"] == "classifier" and route["jev"]["skipped"] is True
    assert s.nl2sql.call_args.kwargs["intent"] is None


def test_without_jev_a_change_it_cannot_plan_also_falls_through(routed):
    run, s = routed
    s.nl2sql.return_value = ("", {"write_request": True})
    s.plan.return_value = CANNOT
    result, route = run("Can you add a Teams meeting to this event?")
    assert result.response == KNOWLEDGE.text and route["fallback"] == "classifier, planner"
    assert s.plan.call_args.args[4] is None  # a new request


OFFER = "add a Microsoft Teams meeting to Sync"


def test_a_plain_yes_to_an_offer_plans_what_was_offered(routed):
    """Not the older waiting plan, and with no Jev decision: the planner is asked for the offered change."""
    run, s = routed
    s.manager.offer_before.return_value = OFFER
    s.plan.return_value = PLAN
    result, route = run("yes please", waiting_plan=MagicMock(questions=[], suggestions=[], draft={}))
    assert result.plan == {"id": "p1"} and route["route"] == "change" and route["shortcut"] is True
    s.decide.assert_not_called() and s.nl2sql.assert_not_called()
    assert s.plan.call_args.args[2] == OFFER and s.plan.call_args.args[4] is None


def test_any_other_reply_to_an_offer_goes_to_jev_with_both_notes(routed):
    run, s = routed
    s.manager.offer_before.return_value = OFFER
    s.decide.return_value = jev("change")
    s.plan.return_value = PLAN
    waiting = MagicMock()
    run("yes, but only for next week's", waiting_plan=waiting)
    assert s.decide.call_args.kwargs == {"plan_waiting": True, "offer": OFFER}
    assert s.plan.call_args.args[2] == "yes, but only for next week's" and s.plan.call_args.args[4] is waiting


def test_a_choice_on_the_waiting_plan_still_answers_it_after_an_offer(routed, monkeypatch):
    """(review, PR #15) FR-001: an offer wins over the waiting plan only for a plain yes"""
    from indico_assistant.services.actions import planner

    monkeypatch.setattr(planner, "answered_draft", lambda plan, message: "draft" if message == "Engineering" else None)
    run, s = routed
    s.manager.offer_before.return_value = OFFER
    s.plan.return_value = PLAN
    waiting = MagicMock(questions=[], suggestions=[], draft={})
    result, route = run("Engineering", waiting_plan=waiting)
    assert route["shortcut"] is True and s.plan.call_args.args[4] is waiting
    s.decide.assert_not_called()


def test_a_plain_no_answers_the_waiting_plan(routed):
    """(review, PR #15) the planner cancels it: left waiting, a later yes to anything would carry it out"""
    run, s = routed
    s.plan.return_value = ("OK, I cancelled that plan; nothing was changed.", {"plan_id": None}, None)
    waiting = MagicMock(questions=[], suggestions=[], draft={})
    result, route = run("no thanks", waiting_plan=waiting)
    assert route["shortcut"] is True and s.plan.call_args.args[4] is waiting
    s.decide.assert_not_called()


def test_a_plain_no_to_an_offer_turns_down_the_offer_not_the_plan(routed):
    run, s = routed
    s.manager.offer_before.return_value = OFFER
    s.decide.return_value = jev("chat")
    run("no", waiting_plan=MagicMock(questions=[], suggestions=[], draft={}))
    s.plan.assert_not_called()
    assert s.decide.call_args.kwargs["offer"] == OFFER


def test_an_offer_the_planner_cannot_plan_gets_a_knowledge_answer_about_the_offer(routed):
    """(review, PR #15) about the offered change, not the word "yes", which would offer it again"""
    run, s = routed
    s.manager.offer_before.return_value = OFFER
    s.plan.return_value = CANNOT
    result, route = run("yes")
    assert result.response == KNOWLEDGE.text and s.knowledge.call_args.args[1] == OFFER


def test_without_jev_an_offer_sends_the_next_message_to_the_planner(routed):
    run, s = routed
    s.manager.offer_before.return_value = OFFER
    s.plan.return_value = PLAN
    result, route = run("sure, for Sync")
    assert result.plan == {"id": "p1"} and route["route"] == "change"
    assert route["fallback"] == "planner first"  # (review, PR #15) the classifier never ran
    s.nl2sql.assert_not_called()


def test_without_jev_the_planner_is_not_asked_twice(routed):
    run, s = routed
    s.manager.offer_before.return_value = OFFER
    s.plan.return_value = CANNOT
    s.nl2sql.return_value = ("", {"write_request": True})
    result, route = run("sure, for Sync")
    assert s.plan.call_count == 1 and result.response == KNOWLEDGE.text and route["fallback"] == "classifier, planner"


def test_the_planners_answer_carries_its_cannot_plan_flag():
    """(found while building: _plan still read the retired flag, and every live planner turn would have failed)"""
    from indico_assistant.services.actions.planner import PlanTurn

    service = ChatService(session_manager=MagicMock(), context_builder=MagicMock())
    plugin = MagicMock(settings=MagicMock(get_all=MagicMock(return_value={})))
    with patch("indico_assistant.plugin.AssistantPlugin") as assistant, \
            patch("indico_assistant.services.actions.context.acting_as"), \
            patch("indico_assistant.services.actions.planner.plan_turn",
                  return_value=PlanTurn("I cannot do that from the chat yet.", cannot_plan=True)):
        assistant.instance = plugin
        reply, metadata, plan = service._plan(MagicMock(), uuid4(), "Can you book a room?", [], None)
    assert (reply, metadata, plan) == ("I cannot do that from the chat yet.", {"plan_id": None, "cannot_plan": True}, None)



def test_the_history_is_the_conversation_before_the_question():
    """For an accepted offer the planner is asked the offer: the bare "yes" must not stay in its history."""
    from indico_assistant.services.chat.service import _history

    talk = [{"role": "user", "content": "can you add Teams?"}, {"role": "assistant", "content": "Shall I?"},
            {"role": "system", "content": "The user is on event 5."}, {"role": "user", "content": "yes"}]
    assert _history(talk) == talk[:-1] and _history(talk[:-1]) == talk[:-1] and _history([]) == []


def test_an_unknown_data_intent_is_recorded_as_the_classifiers(routed):
    run, s = routed
    s.decide.return_value = jev("data", None)
    result, route = run("Who speaks at Q3 planning?")
    assert result.response == "An answer" and route["route"] == "data" and route["fallback"] == "classifier"
    assert s.nl2sql.call_args.kwargs["intent"] is None
