"""A plan runs only after its owner confirms that exact, unexpired, question-free version (data-model.md)."""

from datetime import timedelta

import pytest

from indico_assistant.models import ActionPlan, ChatSession
from indico_assistant.services.actions import executor


@pytest.fixture
def chat(db, dummy_user):
    session = ChatSession(user_id=dummy_user.id)
    db.session.add(session)
    db.session.flush()
    return session


@pytest.fixture
def new_plan(chat, dummy_user):
    def _new(questions=(), supersedes=None):
        return executor.create_plan(dummy_user, chat.id, steps=[{'n': 1, 'action': 'noop', 'args': {}}],
                                    summary='Do nothing', questions=list(questions), supersedes=supersedes)
    return _new


def test_confirm_succeeds_once(new_plan, dummy_user):
    plan, token = new_plan()
    assert executor.confirm(plan.id, dummy_user, token) == 'confirmed'
    assert executor.confirm(plan.id, dummy_user, token) == 'not_confirmable'  # double click, second tab
    assert ActionPlan.query.get(plan.id).status == 'confirmed'


@pytest.mark.parametrize('case', ['wrong_token', 'other_user', 'expired', 'open_question', 'cancelled'])
def test_confirm_refusals(new_plan, dummy_user, create_user, case):
    plan, token = new_plan(questions=[{'id': 'category'}] if case == 'open_question' else ())
    user = dummy_user
    if case == 'wrong_token':
        token = 'guess'
    elif case == 'other_user':
        user = create_user(2)
    elif case == 'expired':
        plan.expires_at -= timedelta(hours=1)
    elif case == 'cancelled':
        assert executor.cancel(plan.id, dummy_user)
    expected = {'wrong_token': 'invalid_token', 'other_user': 'not_found'}.get(case, 'not_confirmable')
    assert executor.confirm(plan.id, user, token) == expected
    assert ActionPlan.query.get(plan.id).status != 'confirmed'


def test_a_revision_supersedes_the_shown_plan(new_plan, dummy_user):
    old, old_token = new_plan()
    new, new_token = new_plan(supersedes=old)
    assert old.status == 'superseded' and new.supersedes_id == old.id
    assert executor.confirm(old.id, dummy_user, old_token) == 'not_confirmable'
    assert new_token != old_token
    assert executor.confirm(new.id, dummy_user, new_token) == 'confirmed'


def test_expiry_is_computed(new_plan):
    plan, _ = new_plan()
    assert plan.effective_status == 'shown' and plan.can_confirm
    plan.expires_at -= timedelta(hours=1)
    assert plan.effective_status == 'expired' and not plan.can_confirm


def test_cancel_only_from_shown(new_plan, dummy_user):
    plan, token = new_plan()
    executor.confirm(plan.id, dummy_user, token)
    assert not executor.cancel(plan.id, dummy_user)


def test_the_open_plan_of_a_chat(new_plan, chat):
    first, _ = new_plan()
    second, _ = new_plan(supersedes=first)
    assert executor.open_plan(chat.id) == second
    second.expires_at -= timedelta(hours=1)
    assert executor.open_plan(chat.id) is None
