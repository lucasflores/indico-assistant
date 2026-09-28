"""The planner's handling of each decision (research R13); drafts come from a fake LLM."""

from unittest.mock import MagicMock, patch

import pytest

from indico_assistant.models import ActionPlan, ChatSession
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
    result = turn(dummy_user, chat, llm_returning(decision='cancel'), open_plan=shown, message='never mind')
    assert 'cancelled' in result.reply and executor.open_plan(chat.id) is None


def test_typed_confirmation_runs_the_open_plan(dummy_user, chat, shown):
    with patch.object(executor, 'run') as run:
        run.return_value = MagicMock(status='done', steps=shown.steps)
        llm = llm_returning(decision='confirm')
        result = turn(dummy_user, chat, llm, open_plan=shown, message='Yes please!')
    run.assert_called_once_with(shown.id, enabled=planner.enabled_actions(ON))  # the admin's switches, as now
    assert result.reply.startswith('Done') and not llm.generate.called  # a plain yes needs no model


@pytest.mark.parametrize(('message', 'steps'), [('ok, and add Makoto', []),
                                                ('yes but make it 3pm', [{'action': 'change_meeting'}])])
def test_the_model_cannot_confirm_for_the_user(dummy_user, chat, shown, message, steps):
    # (code review, PR #3) only a message that is nothing but a yes runs the plan; the model's reading of
    # anything else is at most a revision
    with patch.object(executor, 'run') as run:
        result = turn(dummy_user, chat, llm_returning(decision='confirm', steps=steps), open_plan=shown,
                      message=message)
    run.assert_not_called()
    assert ActionPlan.query.get(shown.id).status in ('shown', 'superseded')
    if not steps:
        assert result.reply == planner.CONFIRM_HOW


def test_typed_confirmation_waits_for_open_questions(dummy_user, chat):
    plan, _ = executor.create_plan(dummy_user, chat.id, summary='x', steps=[{'n': 1, 'action': 'create_event', 'args': {}}],
                                   questions=[{'id': 'category', 'text': 'Which category?'}])
    with patch.object(executor, 'run') as run:
        result = turn(dummy_user, chat, llm_returning(decision='confirm'), open_plan=plan, message='yes')
    run.assert_not_called()
    assert 'questions' in result.reply


def test_confirm_without_an_open_plan_is_just_a_message(dummy_user, chat):
    assert not turn(dummy_user, chat, llm_returning(decision='confirm')).handled


def test_llm_failure_is_a_question_not_an_error(dummy_user, chat):
    llm = MagicMock()
    llm.generate.return_value = MagicMock(success=False)
    assert turn(dummy_user, chat, llm).reply == planner.NOT_UNDERSTOOD



# --- spec 020 US2: "this meeting" follows the page -------------------------------------------------------

def test_this_meeting_stays_this_meeting_unless_the_user_named_it():
    # (seen live: the model wrote the page's title, which also matched the meeting's namesakes on other pages)
    from indico_assistant.services.actions.planner import _the_meeting_the_user_meant
    draft = lambda meeting: PlanDraft.model_validate({'decision': 'new_request', 'steps': [  # noqa: E731
        {'action': 'change_meeting', 'meeting': meeting, 'move_to': {'time': '4pm'}}]})
    assert _the_meeting_the_user_meant(draft('Sync with Makoto'), 'Move this meeting to 4pm').steps[0].meeting == 'this meeting'
    assert _the_meeting_the_user_meant(draft('Sync with Makoto'), 'Move it to 4pm').steps[0].meeting == 'this meeting'
    assert _the_meeting_the_user_meant(draft('Sync with Makoto'), 'Move Sync with Makoto to 4pm').steps[0].meeting == \
        'Sync with Makoto'
    assert _the_meeting_the_user_meant(draft('#354'), 'Move it to 4pm').steps[0].meeting == '#354'  # a chosen answer
    attach = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'attach', 'target': 'my talk at Sync with Makoto', 'upload': 'this'}]})
    assert _the_meeting_the_user_meant(attach, 'attach this to my talk').steps[0].target == 'my talk at Sync with Makoto'


def test_a_revision_that_changes_nothing_is_a_question(dummy_user, chat):
    step = {'action': 'change_meeting', 'meeting': 'this meeting', 'move_to': {'time': '4pm'}}
    waiting, _ = executor.create_plan(dummy_user, chat.id, summary='Move it', steps=[],
                                      draft={'decision': 'new_request', 'steps': [step], 'topic': 'move it'})
    result = turn(dummy_user, chat, llm_returning(decision='revise', steps=[step]), open_plan=waiting,
                  message='What is this event about?')
    assert not result.handled  # answered as a question (NL2SQL), the plan still waiting
    assert ActionPlan.query.get(waiting.id).status == 'shown'



@pytest.mark.parametrize(('message', 'question'), [
    ('What is this event about?', True), ('Who are the speakers?', True), ('When does it start?', True),
    ('Can you move it to 3pm?', False), ('What if we make it 30 minutes?', False), ('make it an hour', False),
    ('How about moving it earlier?', False), ('Why not renaming it?', False), ('Which setup do we use?', False),
])
def test_a_plain_question_never_revises_the_waiting_plan(message, question):
    from indico_assistant.services.actions.planner import _only_a_question
    assert _only_a_question(message) is question



@pytest.mark.parametrize(('message', 'cancelled'), [('What is this event about?', False), ('cancel that', True),
                                                     ('never mind', True), ('Tell me about the speakers', False)])
def test_only_the_user_cancels_the_waiting_plan(dummy_user, chat, shown, message, cancelled):
    # (seen live: the model answered "What is this event about?" on another page with "cancel")
    result = turn(dummy_user, chat, llm_returning(decision='cancel'), open_plan=shown, message=message)
    assert (ActionPlan.query.get(shown.id).status == 'cancelled') is cancelled
    assert result.handled is cancelled  # otherwise answered as a question
