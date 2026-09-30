"""The planner says when it found nothing to change (spec 022, FR-003): the chat then gives the knowledge answer."""

import pytest

from indico_assistant.models import ChatSession
from indico_assistant.services.actions import planner, resolve
from indico_assistant.services.llm.models.plan import PlanDraft

from .test_planner import ON, llm_returning


@pytest.fixture
def chat(db, dummy_user):
    chat = ChatSession(user_id=dummy_user.id)
    db.session.add(chat)
    db.session.flush()
    return chat


def _turn(user, chat, llm, message="Can you create meetings for me?"):
    return planner.plan_turn(user, chat.id, message, [], None, llm=llm, settings=ON)


def test_a_draft_without_steps(dummy_user, chat):
    result = _turn(dummy_user, chat, llm_returning(decision="new_request", steps=[], reply=""))
    assert result.nothing_to_change and result.reply == planner.NOT_UNDERSTOOD and result.plan is None


def test_the_resolver_finding_nothing_to_change(dummy_user, chat, monkeypatch):
    monkeypatch.setattr(resolve, "draft_to_plan", lambda *a, **kw: resolve.Resolved(refusal=resolve.NOTHING_TO_CHANGE))
    draft = {"decision": "new_request", "steps": [{"action": "change_meeting", "meeting": "it"}]}
    assert _turn(dummy_user, chat, llm_returning(**draft)).nothing_to_change


def test_a_real_refusal_is_not_nothing_to_change(dummy_user, chat, monkeypatch):
    monkeypatch.setattr(resolve, "draft_to_plan",
                        lambda *a, **kw: resolve.Resolved(refusal="You cannot manage “Sync”, so I cannot change it."))
    draft = {"decision": "new_request", "steps": [{"action": "change_meeting", "meeting": "Sync"}]}
    result = _turn(dummy_user, chat, llm_returning(**draft))
    assert not result.nothing_to_change and "cannot manage" in result.reply


def test_a_failed_model_call_is_not_nothing_to_change(dummy_user, chat):
    from unittest.mock import MagicMock

    llm = MagicMock()
    llm.generate.return_value = MagicMock(success=False, result=None, error="timeout")
    assert not _turn(dummy_user, chat, llm).nothing_to_change


def test_the_draft_model_still_validates():
    assert PlanDraft.model_validate({"decision": "new_request", "steps": []}).steps == []
