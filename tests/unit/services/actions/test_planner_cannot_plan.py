"""The planner says when it cannot plan a message (spec 022): the chat then gives the knowledge answer."""

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
    assert result.cannot_plan and result.reply == planner.NOT_UNDERSTOOD and result.plan is None


def test_the_resolver_finding_cannot_plan(dummy_user, chat, monkeypatch):
    monkeypatch.setattr(resolve, "draft_to_plan", lambda *a, **kw: resolve.Resolved(refusal=resolve.NOTHING_TO_CHANGE))
    draft = {"decision": "new_request", "steps": [{"action": "change_meeting", "meeting": "it"}]}
    assert _turn(dummy_user, chat, llm_returning(**draft)).cannot_plan


def test_a_real_refusal_is_not_cannot_plan(dummy_user, chat, monkeypatch):
    monkeypatch.setattr(resolve, "draft_to_plan",
                        lambda *a, **kw: resolve.Resolved(refusal="You cannot manage “Sync”, so I cannot change it."))
    draft = {"decision": "new_request", "steps": [{"action": "change_meeting", "meeting": "Sync"}]}
    result = _turn(dummy_user, chat, llm_returning(**draft))
    assert not result.cannot_plan and "cannot manage" in result.reply


def test_a_failed_model_call_is_not_cannot_plan(dummy_user, chat):
    from unittest.mock import MagicMock

    llm = MagicMock()
    llm.generate.return_value = MagicMock(success=False, result=None, error="timeout")
    assert not _turn(dummy_user, chat, llm).cannot_plan


def test_the_draft_model_still_validates():
    assert PlanDraft.model_validate({"decision": "new_request", "steps": []}).steps == []


def test_changes_switched_off(dummy_user, chat):
    result = planner.plan_turn(dummy_user, chat.id, "Can you add a reminder?", [], None, llm=llm_returning(decision="unrelated"),
                               settings={"actions_enabled": False})
    assert result.cannot_plan and result.reply == planner.NOT_AVAILABLE


def test_an_action_it_does_not_have(dummy_user, chat, monkeypatch):
    def unsupported(*args, **kwargs):
        raise NotImplementedError
    monkeypatch.setattr(resolve, "draft_to_plan", unsupported)
    draft = {"decision": "new_request", "steps": [{"action": "change_meeting", "meeting": "it"}]}
    result = _turn(dummy_user, chat, llm_returning(**draft))
    assert result.cannot_plan and result.reply == planner.NOT_SUPPORTED


def test_exact_replies_to_a_waiting_plan(dummy_user, chat, monkeypatch):
    """The shortcut (spec 022): a plain yes, or a choice the plan offered, needs neither Jev nor a model."""
    plan = type("Plan", (), {"questions": [], "suggestions": [], "draft": {}})()
    monkeypatch.setattr(planner, "answered_draft", lambda open_plan, message: "draft" if message == "Home" else None)
    monkeypatch.setattr(planner, "accepted_suggestion", lambda open_plan, message: None)
    assert planner.exact_reply(plan, "yes please") and planner.exact_reply(plan, "OK!")
    assert planner.exact_reply(plan, "Home")  # a button / a typed choice
    assert not planner.exact_reply(plan, "yes, but make it 3pm") and not planner.exact_reply(plan, "who is coming?")
    assert not planner.exact_reply(None, "yes")
    assert planner.exact_reply(plan, "no") and planner.exact_reply(plan, "Cancel it.") and planner.exact_reply(plan, "never mind")
    assert not planner.exact_reply(plan, "no, make it 3pm")
    assert planner.shortcut(plan, "nope")[0].decision == "cancel" and planner.shortcut(plan, "yes")[0].decision == "confirm"



def test_an_action_the_admin_switched_off(dummy_user, chat, monkeypatch):
    step = {"n": 1, "action": "update_event", "args": {}, "refs": {}}  # ON allows create_event only
    monkeypatch.setattr(resolve, "draft_to_plan", lambda *a, **kw: resolve.Resolved(steps=[step]))
    draft = {"decision": "new_request", "steps": [{"action": "change_meeting", "meeting": "it"}]}
    result = _turn(dummy_user, chat, llm_returning(**draft))
    assert result.cannot_plan and "update_event is not available" in result.reply


def test_a_plan_too_big_is_the_planners_to_explain(dummy_user, chat, monkeypatch):
    steps = [{"n": n, "action": "create_event", "args": {}, "refs": {}} for n in range(1, 27)]
    monkeypatch.setattr(resolve, "draft_to_plan", lambda *a, **kw: resolve.Resolved(steps=steps))
    draft = {"decision": "new_request", "steps": [{"action": "change_meeting", "meeting": "it"}]}
    result = _turn(dummy_user, chat, llm_returning(**draft))
    assert not result.cannot_plan and "at most 25 steps" in result.reply
