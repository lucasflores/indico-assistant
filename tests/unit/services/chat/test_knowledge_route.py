"""Knowledge questions get the knowledge answer, and every answer records its route (spec 022, FR-002 and FR-020)."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from indico_assistant.services.chat.service import ChatService
from indico_assistant.services.knowledge.answer import KnowledgeResult


@pytest.fixture
def routed():
    """answer() with the planner, NL2SQL and the knowledge answer stubbed; returns (run, stubs, stored metadata)."""
    manager, context = MagicMock(), MagicMock()
    service = ChatService(session_manager=manager, context_builder=context)
    session_id = uuid4()
    manager.get_session.return_value = MagicMock(id=session_id, event_id=None)
    manager.add_assistant_message.return_value = MagicMock(id=uuid4())
    manager.offer_before.return_value = None
    context.build_context.return_value = [{"role": "user", "content": "How do I lock my event?"}]
    context.page_note.return_value = None
    stubs = MagicMock()
    stubs.plan.return_value = None
    stubs.nl2sql.return_value = ("An answer", {})
    stubs.knowledge.return_value = KnowledgeResult("Use the gear menu, then Lock.", guide_commit="e7e0016",
                                                   guide_pages=["https://learn.getindico.io/meetings/creating/"])

    def run(message="How do I lock my event?"):
        with patch.object(service, "_load_user", return_value=MagicMock(id=1, is_admin=False)), \
                patch.object(service, "_plan", stubs.plan), \
                patch.object(service, "_process_with_nl2sql", stubs.nl2sql), \
                patch.object(service, "_knowledge", stubs.knowledge), \
                patch("indico_assistant.services.actions.executor.open_plan", return_value=None), \
                patch("indico_assistant.services.chat.service.db"):
            result = service.answer(1, session_id, message)
        stored = manager.add_assistant_message.call_args.args[2]
        return result, stored
    return run, stubs


def test_a_knowledge_question_gets_the_knowledge_answer(routed):
    run, stubs = routed
    stubs.nl2sql.return_value = ("", {"knowledge_request": True})
    result, stored = run()
    assert result.response == "Use the gear menu, then Lock."
    assert stored["route"]["route"] == "knowledge" and stored["route"]["fallback"] == "classifier"
    assert stored["route"]["guide_commit"] == "e7e0016"
    stubs.plan.assert_not_called()


def test_a_data_question_keeps_its_route_and_is_recorded(routed):
    run, stubs = routed
    result, stored = run("Who speaks tomorrow?")
    assert result.response == "An answer" and stored["route"]["route"] == "data"
    stubs.knowledge.assert_not_called()


def test_a_change_request_keeps_its_route_and_is_recorded(routed):
    run, stubs = routed
    stubs.nl2sql.return_value = ("", {"write_request": True})
    stubs.plan.return_value = ("Here is the plan.", {"plan_id": "p1"}, {"id": "p1"})
    result, stored = run("Move it to 3pm")
    assert result.plan == {"id": "p1"} and stored["route"]["route"] == "change"
    stubs.knowledge.assert_not_called()


def test_a_failed_knowledge_answer_still_replies(routed):
    run, stubs = routed
    stubs.nl2sql.return_value = ("", {"knowledge_request": True})
    stubs.knowledge.return_value = KnowledgeResult("I could not answer that just now.", failed=True)
    result, stored = run()
    assert result.response == "I could not answer that just now." and stored["route"]["failed"] is True
