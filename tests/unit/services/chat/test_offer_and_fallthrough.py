"""Follow-ups (spec 022, US3): the knowledge gate goes first, an offer sends the next message to the planner, and
a planner that finds nothing to change hands over to the knowledge answer (FR-001 to FR-005)."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from indico_assistant.services.chat.service import ChatService
from indico_assistant.services.knowledge.answer import KnowledgeResult
from indico_assistant.services.knowledge.gate import GateResult

KNOWLEDGE = KnowledgeResult("Open the Videoconference page.", offer=None, guide_commit="e7e0016")
PLAN = ("Here is the plan.", {"plan_id": "p1", "nothing_to_change": False}, {"id": "p1"})
NOTHING = ("I could not work out what to change.", {"plan_id": None, "nothing_to_change": True}, None)


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
    s.gate.return_value = (GateResult(None, True, "no key"), False)
    s.plan.return_value = None
    s.nl2sql.return_value = ("An answer", {})
    s.knowledge.return_value = KNOWLEDGE

    def run(message="hi", waiting_plan=None):
        with patch.object(service, "_load_user", return_value=MagicMock(id=1, is_admin=False)), \
                patch.object(service, "_gate", s.gate), patch.object(service, "_plan", s.plan), \
                patch.object(service, "_process_with_nl2sql", s.nl2sql), patch.object(service, "_knowledge", s.knowledge), \
                patch("indico_assistant.services.actions.executor.open_plan", return_value=waiting_plan), \
                patch("indico_assistant.services.chat.service.db"):
            result = service.answer(1, session_id, message, message_id=uuid4())
        return result, manager.add_assistant_message.call_args.args[2]["route"]
    s.manager = manager
    return run, s


def test_the_gate_goes_first(routed):
    run, s = routed
    s.gate.return_value = (GateResult(0.6, False, "score"), True)
    result, route = run("how would I do it myself?", waiting_plan=MagicMock())
    assert result.response == KNOWLEDGE.text and route["route"] == "knowledge"
    assert (route["gate"], route["gate_score"], route["gate_skipped"], route["fallback"]) == \
        ("typesafe/jev-1.13", 0.6, False, None)
    s.plan.assert_not_called() and s.nl2sql.assert_not_called()


def test_below_the_cut_off_routing_continues(routed):
    run, s = routed
    s.gate.return_value = (GateResult(0.05, False, "score"), False)
    result, route = run("Who speaks tomorrow?")
    assert result.response == "An answer" and route["route"] == "data" and route["gate_score"] == 0.05
    s.knowledge.assert_not_called()


def test_an_offer_sends_the_next_message_to_the_planner(routed):
    run, s = routed
    s.manager.offer_before.return_value = "add a Microsoft Teams meeting to Sync"
    s.plan.return_value = PLAN
    result, route = run("yes please")
    assert result.plan == {"id": "p1"} and route["route"] == "change"
    assert s.plan.call_args.args[4] is None  # no waiting plan: the offer is in the history
    s.nl2sql.assert_not_called()


def test_after_an_offer_a_message_without_a_change_is_routed_as_usual(routed):
    run, s = routed
    s.manager.offer_before.return_value = "add a Microsoft Teams meeting to Sync"
    s.plan.side_effect = [None, None]  # "thanks": unrelated
    result, route = run("thanks")
    assert result.response == "An answer" and route["route"] == "data"


def test_after_an_offer_nothing_to_change_is_routed_as_usual(routed):
    run, s = routed
    s.manager.offer_before.return_value = "add a Microsoft Teams meeting to Sync"
    s.plan.return_value = NOTHING
    result, route = run("who else is coming?")
    assert result.response == "An answer" and route["route"] == "data"


def test_nothing_to_change_hands_over_to_the_knowledge_answer(routed):
    run, s = routed
    s.nl2sql.return_value = ("", {"write_request": True})
    s.plan.return_value = NOTHING
    result, route = run("Can you add a Teams meeting to this event?")
    assert result.response == KNOWLEDGE.text and route["route"] == "knowledge"
    assert route["fallback"] == "planner_nothing_to_change" and result.plan is None


def test_with_a_waiting_plan_the_planners_reply_stands(routed):
    run, s = routed
    s.plan.return_value = NOTHING
    result, route = run("hmm", waiting_plan=MagicMock())
    assert result.response == NOTHING[0] and route["route"] == "change"
    s.knowledge.assert_not_called()


def test_an_offer_is_recorded(routed):
    run, s = routed
    s.nl2sql.return_value = ("", {"knowledge_request": True})
    s.knowledge.return_value = KnowledgeResult("Yes, I can. Shall I?", offer="add a Teams meeting")
    _, route = run("Can you add a Teams meeting?")
    assert route["offer"] == "add a Teams meeting" and route["fallback"] == "classifier"
