"""The planner's handling of each decision (research R13); drafts come from a fake LLM."""

from unittest.mock import MagicMock, patch

import pytest

from indico_assistant.models import ChatSession
from indico_assistant.services.actions import executor, planner
from indico_assistant.services.llm.models.base import LLMResponse
from indico_assistant.services.llm.models.plan import PlanDraft


ON = {'actions_enabled': True, 'actions_allowed': ['create_event']}


@pytest.fixture
def chat(db, dummy_user):
    chat = ChatSession(user_id=dummy_user.id)
    db.session.add(chat)
    db.session.flush()
    return chat


def llm_returning(**draft):
    llm = MagicMock()
    llm.generate.return_value = LLMResponse(success=True, latency_ms=1, result=PlanDraft.model_validate({'reply': 'OK', **draft}))
    return llm


def turn(user, chat, llm, open_plan=None, settings=ON, message='hi'):
    return planner.plan_turn(user, chat.id, message, [{'role': 'user', 'content': 'earlier'}], open_plan,
                             llm=llm, settings=settings)


@pytest.fixture
def shown(chat, dummy_user):
    plan, _ = executor.create_plan(dummy_user, chat.id, summary='Create “Sync”',
                                   steps=[{'n': 1, 'action': 'create_event', 'args': {}}])
    return plan


def test_switched_off_means_no_llm_call(dummy_user, chat):
    llm = MagicMock()
    result = turn(dummy_user, chat, llm, settings={'actions_enabled': False})
    assert result.reply == planner.NOT_AVAILABLE and result.plan is None
    llm.generate.assert_not_called()


def test_the_chat_goes_to_the_llm_as_turns(dummy_user, chat):
    llm = llm_returning(decision='unrelated')
    turn(dummy_user, chat, llm)
    assert llm.generate.call_args.kwargs['messages'] == [{'role': 'user', 'content': 'earlier'}]
    assert 'Message: hi' in llm.generate.call_args.args[0]


def test_unrelated_follow_up_goes_back_to_questions(dummy_user, chat, shown):
    assert not turn(dummy_user, chat, llm_returning(decision='unrelated'), open_plan=shown).handled
    assert shown.status == 'shown'


def test_cancel(dummy_user, chat, shown):
    result = turn(dummy_user, chat, llm_returning(decision='cancel'), open_plan=shown)
    assert 'cancelled' in result.reply and executor.open_plan(chat.id) is None


def test_typed_confirmation_runs_the_open_plan(dummy_user, chat, shown):
    with patch.object(executor, 'run') as run:
        run.return_value = MagicMock(status='done', steps=shown.steps)
        result = turn(dummy_user, chat, llm_returning(decision='confirm'), open_plan=shown)
    run.assert_called_once_with(shown.id)
    assert result.reply.startswith('Done')


def test_typed_confirmation_waits_for_open_questions(dummy_user, chat):
    plan, _ = executor.create_plan(dummy_user, chat.id, summary='x', steps=[{'n': 1, 'action': 'create_event', 'args': {}}],
                                   questions=[{'id': 'category', 'text': 'Which category?'}])
    with patch.object(executor, 'run') as run:
        result = turn(dummy_user, chat, llm_returning(decision='confirm'), open_plan=plan)
    run.assert_not_called()
    assert 'questions' in result.reply


def test_confirm_without_an_open_plan_is_just_a_message(dummy_user, chat):
    assert not turn(dummy_user, chat, llm_returning(decision='confirm')).handled


def test_llm_failure_is_a_question_not_an_error(dummy_user, chat):
    llm = MagicMock()
    llm.generate.return_value = MagicMock(success=False)
    assert turn(dummy_user, chat, llm).reply == planner.NOT_UNDERSTOOD
