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
    # a meeting the user named stays theirs, even with an "it" in the message, and even if the model returns the
    # full title (review, PR #5, rounds 2 and 3)
    kept = lambda title, message, page='Sync with Makoto': _the_meeting_the_user_meant(  # noqa: E731
        draft(title), message, page).steps[0].meeting
    assert kept('ATLAS Weekly Software Meeting', 'Move the ATLAS weekly to Friday, it clashes') == \
        'ATLAS Weekly Software Meeting'
    assert kept('Budget Review 2026', 'Cancel the budget review, it is not needed') == 'Budget Review 2026'
    assert kept('CMS Weekly Call', 'Move the CMS call to 3pm, it overlaps') == 'CMS Weekly Call'
    # ... but words the page's meeting shares describe the page: Sync with Makoto (from earlier) is not meant
    assert kept('Sync with Makoto', 'Move this meeting with Makoto to 4pm', page='Planning with Makoto') == \
        'this meeting'
    assert kept('Sync with Makoto', 'Move it to 4pm', page='Planning with Makoto') == 'this meeting'
    worded = draft('Sync with Makoto')
    worded.reply = 'Sync with Makoto will be moved to 4pm.'
    assert _the_meeting_the_user_meant(worded, 'Move it to 4pm', 'Planning with Makoto').reply == ''  # (not shown)
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



@pytest.mark.parametrize('decision', ['revise', 'new_request'])
def test_a_plain_question_is_no_request_while_a_plan_waits(dummy_user, chat, shown, decision):
    # (seen live: on another page the model answered "What is this event about?" by repeating the waiting request)
    step = {'action': 'change_meeting', 'meeting': 'this meeting', 'move_to': {'time': '16:00'}}
    result = turn(dummy_user, chat, llm_returning(decision=decision, steps=[step]), open_plan=shown,
                  message='What is this event about?')
    assert not result.handled and ActionPlan.query.get(shown.id).status == 'shown'


@pytest.mark.parametrize(('message', 'question'), [
    ('What is this event about?', True), ('Who are the speakers?', True), ('When does it start?', True),
    ('Can you move it to 3pm?', False), ('What if we make it 30 minutes?', False), ('make it an hour', False),
    ('How about moving it earlier?', False), ('Why not renaming it?', False), ('Which setup do we use?', False),
    # a change offered as a question (review, PR #5)
    ('How about 4pm?', False), ('What about Friday at 10?', False), ('Why not Thursday?', False),
    ('Tell me about the speakers', True), ('How long is it?', True),
])
def test_a_plain_question_never_revises_the_waiting_plan(message, question):
    from indico_assistant.services.actions.planner import _only_a_question
    assert _only_a_question(message) is question



@pytest.mark.parametrize(('message', 'cancelled'), [
    ('What is this event about?', False), ('cancel that', True), ('never mind', True),
    ('Tell me about the speakers', False),
    # the model's cancel is the user's unless the message is a plain question (review, PR #5)
    ('Scratch that', True), ('Abort', True), ('I changed my mind', True), ("Let's not", True),
    ('Actually, skip it', True),
])
def test_only_the_user_cancels_the_waiting_plan(dummy_user, chat, shown, message, cancelled):
    # (seen live: the model answered "What is this event about?" on another page with "cancel")
    result = turn(dummy_user, chat, llm_returning(decision='cancel'), open_plan=shown, message=message)
    assert (ActionPlan.query.get(shown.id).status == 'cancelled') is cancelled
    assert result.handled is cancelled  # otherwise answered as a question


# --- spec 021 R4: a turn says when the change did not go through, so the chat can offer a report -----------

def test_switched_off_cannot_do_it(dummy_user, chat):
    assert turn(dummy_user, chat, MagicMock(), settings={'actions_enabled': False}).problem == 'cannot_do'


def test_a_failed_planning_call_was_not_understood(dummy_user, chat):
    llm = MagicMock()
    llm.generate.return_value = MagicMock(success=False)
    assert turn(dummy_user, chat, llm).problem == 'not_understood'


def test_no_steps_and_no_reply_is_not_understood(dummy_user, chat):
    result = turn(dummy_user, chat, llm_returning(decision='new_request', reply=''))
    assert result.reply == planner.NOT_UNDERSTOOD and result.problem == 'not_understood'


def test_a_clarifying_question_is_no_problem(dummy_user, chat, shown):
    # (second fresh review, PR #16: "How long should it be?" under a waiting plan carried a report offer)
    result = turn(dummy_user, chat, llm_returning(decision='revise', reply='How long should it be?'), open_plan=shown,
                  message='make it longer')
    assert result.reply == 'How long should it be?' and result.problem is None


@pytest.mark.parametrize('outcome', ['unsupported', 'refused', 'invalid'])
def test_a_change_it_cannot_make_is_flagged(dummy_user, chat, outcome):
    draft = PlanDraft(decision='new_request', steps=[{'action': 'undo'}])
    resolved = MagicMock(refusal='You cannot manage that event.' if outcome == 'refused' else None, steps=[])
    with patch('indico_assistant.services.actions.resolve.draft_to_plan',
               side_effect=NotImplementedError if outcome == 'unsupported' else None, return_value=resolved), \
            patch.object(planner, 'validate_plan', return_value=['too many steps'] if outcome == 'invalid' else []):
        result = planner._apply(draft, dummy_user, chat.id, None, ['create_event'], [], ON)
    assert result.problem == 'cannot_do' and result.plan is None


def test_a_cancel_is_no_problem(dummy_user, chat, shown):
    assert turn(dummy_user, chat, llm_returning(decision='cancel'), open_plan=shown, message='cancel it').problem is None



@pytest.mark.parametrize(('status', 'problem'), [('done', None), ('failed', 'cannot_do'), ('refused', 'cannot_do')])
def test_a_confirmed_plan_that_did_not_run_is_flagged(dummy_user, chat, shown, status, problem):
    # (fresh review, PR #16: a typed "yes" whose plan then failed said nothing was changed, with no report offer)
    def ran(plan_id, enabled=None):
        shown.status, shown.error = status, None if status == 'done' else 'boom'
        return shown
    with patch.object(executor, 'confirm_typed', return_value='confirmed'), patch.object(executor, 'run', ran), \
            patch('indico_assistant.tasks.actions.outcome_message', return_value='outcome'):
        result = turn(dummy_user, chat, MagicMock(), open_plan=shown, message='yes')
    assert result.reply == 'outcome' and result.problem == problem
