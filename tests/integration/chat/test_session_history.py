"""Conversations the panel reads back (spec 020, Phase 2): a session made under the browser's id, the job of
an unanswered question, pages walked with a cursor, titles, and the caller's own feedback."""

from datetime import timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

import indico_assistant.controllers.chat as chat_module
import indico_assistant.controllers.feedback as feedback_module
import indico_assistant.controllers.sessions as sessions_module
from indico_assistant.controllers.chat import RHChat
from indico_assistant.controllers.feedback import RHFeedback, RHFeedbackDelete
from indico_assistant.controllers.sessions import (
    RHSessionDelete,
    RHSessionDetail,
    RHSessionList,
    RHSessionOpen,
    RHSessionRename,
)
from indico_assistant.models import ChatMessage, ChatSession
from indico_assistant.models.feedback import FeedbackEntry
from indico_assistant.services.chat.session_manager import get_session_manager


@pytest.fixture(autouse=True)
def fresh_chat_service(monkeypatch):
    # (unit tests build the get_chat_service() singleton around mocks; these tests need the real one)
    import indico_assistant.services.chat.service as service_module
    monkeypatch.setattr(service_module, '_chat_service', None)


@pytest.fixture
def users(create_user):
    return {'lucas': create_user(20, first_name='Lucas'), 'makoto': create_user(21, first_name='Makoto')}


def call(rh_class, user, module, monkeypatch, *, args=None, json=None, view_args=None):
    request = MagicMock()
    request.args = args or {}
    request.get_json.return_value = json
    request.view_args = view_args or {}
    monkeypatch.setattr(module, 'request', request)
    monkeypatch.setattr('indico_assistant.controllers.base.get_rate_limiter', MagicMock())
    rh = rh_class.__new__(rh_class)
    rh._user = user
    response, status = rh._process()
    return status, response.get_json() if hasattr(response, 'get_json') else None  # (204s have no body)


def session_of(db, user, *messages, title=None, age_minutes=0):
    chat = ChatSession(user_id=user.id, title=title)
    db.session.add(chat)
    db.session.flush()
    for role, content in messages:
        db.session.add(ChatMessage(session_id=chat.id, role=role, content=content))
    db.session.flush()
    chat.updated_at = chat.updated_at - timedelta(minutes=age_minutes)
    db.session.flush()
    return chat


# --- T005: the session manager -------------------------------------------------------------------------

def test_a_session_can_be_created_under_a_given_id(db, users):
    wanted = uuid4()
    chat = get_session_manager().create_session(users['lucas'].id, None, session_id=wanted)
    assert chat.id == wanted and ChatSession.query.get(wanted).user_id == users['lucas'].id


def test_an_untitled_session_is_named_after_its_first_question(db, users):
    chat = session_of(db, users['lucas'], ('user', 'Who are the speakers of the Q4 budget review and when do they talk?'),
                      ('assistant', 'Makoto and Lucas.'))
    assert get_session_manager().title_of(chat) == 'Who are the speakers of the Q4 budget review and when do…'  # a word cut
    chat.title = 'Budget speakers'
    assert get_session_manager().title_of(chat) == 'Budget speakers'


# --- T006: POST /chat ----------------------------------------------------------------------------------

@pytest.fixture
def queued(monkeypatch):
    task = MagicMock()
    monkeypatch.setattr('indico_assistant.tasks.chat.answer_chat', task)
    monkeypatch.setattr(chat_module.jobs, 'create', lambda user_id, session_id: 'job-1')
    return task


def test_a_message_under_a_new_id_starts_that_session(db, users, monkeypatch, queued):
    thread_id = uuid4()  # chosen by Chainlit (spec 020 R5)
    status, body = call(RHChat, users['lucas'], chat_module, monkeypatch,
                        json={'message': 'hello', 'session_id': str(thread_id)})
    assert status == 202 and body['session_id'] == str(thread_id) and body['created_session']
    assert ChatSession.query.get(thread_id).user_id == users['lucas'].id


def test_someone_elses_session_id_is_refused(db, users, monkeypatch, queued):
    theirs = session_of(db, users['makoto'], ('user', 'mine'))
    status, _ = call(RHChat, users['lucas'], chat_module, monkeypatch,
                     json={'message': 'hello', 'session_id': str(theirs.id)})
    assert status == 403 and ChatMessage.query.filter_by(session_id=theirs.id).count() == 1


def test_the_job_is_kept_on_the_question(db, users, monkeypatch, queued):
    status, body = call(RHChat, users['lucas'], chat_module, monkeypatch, json={'message': 'hello'})
    question = ChatMessage.query.filter_by(session_id=body['session_id'], role='user').one()
    assert status == 202 and question.metadata_json['job_id'] == 'job-1'


# --- T007: GET /sessions and GET /sessions/<id> ---------------------------------------------------------

def test_pages_are_walked_with_a_cursor_newest_first(db, users, monkeypatch):
    chats = [session_of(db, users['lucas'], ('user', f'question {n}'), age_minutes=n) for n in range(5)]
    session_of(db, users['makoto'], ('user', 'not mine'))
    session_of(db, users['lucas'])  # nothing said in it: not listed
    session_of(db, users['lucas'], ('assistant', 'Done: …'))  # nor only the assistant (a plan's outcome)
    seen, cursor = [], None
    while True:
        status, body = call(RHSessionList, users['lucas'], sessions_module, monkeypatch,
                            args={'limit': '2', **({'cursor': cursor} if cursor else {})})
        assert status == 200
        seen += [s['session_id'] for s in body['sessions']]
        if not (cursor := body['next_cursor']):
            break
        chats[4].touch()  # the oldest is used between pages: it moves to the top (seen on the next refresh)
        db.session.flush()
    assert seen == [str(c.id) for c in chats[:4]]  # each once, in order; nothing shifted into a repeat
    assert body['sessions'] == [] or body['sessions'][-1]['title'] == 'question 3'
    _, first = call(RHSessionList, users['lucas'], sessions_module, monkeypatch, args={'limit': '1'})
    assert first['sessions'][0]['session_id'] == str(chats[4].id) and first['sessions'][0]['title'] == 'question 4'
    assert 'updated_at' in first['sessions'][0]


def test_a_page_counts_and_names_its_rows_in_a_fixed_number_of_queries(db, users, monkeypatch):
    from sqlalchemy import event

    session_of(db, users['lucas'], ('user', 'First question here'), ('assistant', 'a'), ('user', 'later'))
    session_of(db, users['lucas'], ('user', 'q'), title='Renamed')
    for n in range(8):
        session_of(db, users['lucas'], ('user', f'filler {n}'), age_minutes=10 + n)
    statements = []
    listen = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(db.engine, 'before_cursor_execute', listen)
    try:
        _, body = call(RHSessionList, users['lucas'], sessions_module, monkeypatch, args={'limit': '10'})
    finally:
        event.remove(db.engine, 'before_cursor_execute', listen)
    rows = {s['title']: s for s in body['sessions']}
    assert rows['First question here']['message_count'] == 3 and rows['Renamed']['message_count'] == 1
    assert len(statements) <= 5  # the page, the total, counts, first questions: not ~3 per row (PR #5 review)


@pytest.mark.parametrize('cursor', ['not-base64!', 'bm90IGEgY3Vyc29y', 'eHx5'])
def test_a_bad_cursor_is_refused_not_a_server_error(db, users, monkeypatch, cursor):
    status, body = call(RHSessionList, users['lucas'], sessions_module, monkeypatch, args={'cursor': cursor})
    assert status == 422 and body['error'] == 'VALIDATION_ERROR'


@pytest.mark.parametrize('rh', [RHSessionRename, RHSessionOpen])
def test_a_body_that_is_not_an_object_is_no_server_error(db, users, monkeypatch, rh):
    chat = session_of(db, users['lucas'], ('user', 'q'))
    status, _ = call(rh, users['lucas'], sessions_module, monkeypatch, json=['x'],
                     view_args={'session_id': str(chat.id)})
    assert status in (200, 422)


@pytest.mark.parametrize(('job', 'reported'), [({'status': 'pending'}, True), ({'status': 'failed'}, False),
                                                ({'status': 'done'}, False), (None, False)])
def test_an_unanswered_question_reports_its_job_only_while_it_runs(db, users, monkeypatch, job, reported):
    # (review, PR #5: a failed or expired job's error came back on every page)
    chat = session_of(db, users['lucas'], ('user', 'first'), ('assistant', 'answer'))
    view = {'session_id': str(chat.id)}
    monkeypatch.setattr(sessions_module.jobs, 'get', lambda job_id: job)
    status, body = call(RHSessionDetail, users['lucas'], sessions_module, monkeypatch, view_args=view)
    assert status == 200 and body.get('pending_job_id') is None
    db.session.add(ChatMessage(session_id=chat.id, role='user', content='second',
                               metadata_json={'job_id': 'job-2', 'event_id': 351}))
    db.session.flush()
    _, body = call(RHSessionDetail, users['lucas'], sessions_module, monkeypatch, view_args=view)
    assert (body.get('pending_job_id') == 'job-2') is reported and body['title'] == 'first'
    assert body['messages'][-1]['metadata']['event_id'] == 351


def test_the_detail_names_the_waiting_plan_and_can_skip_the_messages(db, users, monkeypatch):
    from indico_assistant.services.actions import executor
    chat = session_of(db, users['lucas'], ('user', 'move it'))
    view = {'session_id': str(chat.id)}
    _, body = call(RHSessionDetail, users['lucas'], sessions_module, monkeypatch, view_args=view)
    assert body.get('waiting_plan_id') is None
    plan, _ = executor.create_plan(users['lucas'], chat.id, summary='Move it', steps=[])
    _, body = call(RHSessionDetail, users['lucas'], sessions_module, monkeypatch, view_args=view)
    assert body['waiting_plan_id'] == str(plan.id)
    status, light = call(RHSessionDetail, users['lucas'], sessions_module, monkeypatch, view_args=view,
                         args={'messages': '0'})
    assert status == 200 and light == {'session_id': str(chat.id)}
    status, _ = call(RHSessionDetail, users['makoto'], sessions_module, monkeypatch, view_args=view,
                     args={'messages': '0'})
    assert status == 403  # (still the owner's only)


def test_the_detail_never_shows_an_answers_evidence(db, users, monkeypatch):
    # spec 021 R5: the evidence is for the team's triage; the owner already sees the query, not the checks
    chat = session_of(db, users['lucas'], ('user', 'When is the Sync?'))
    db.session.add(ChatMessage(session_id=chat.id, role='assistant', content='Tomorrow.',
                               metadata_json={'sql_generated': 'SELECT 1',
                                              'evidence': {'validation_rejection': 'forbidden keyword'}}))
    db.session.flush()
    _, body = call(RHSessionDetail, users['lucas'], sessions_module, monkeypatch, view_args={'session_id': str(chat.id)})
    answer = body['messages'][-1]['metadata']
    assert 'evidence' not in answer and answer['sql_generated'] == 'SELECT 1'


def test_search_takes_percent_and_underscore_literally(db, users, monkeypatch):
    session_of(db, users['lucas'], ('user', 'Budget up 100% this year'))
    session_of(db, users['lucas'], ('user', 'Budget up 1000 this year'))
    session_of(db, users['lucas'], ('user', 'file_name please'))
    session_of(db, users['lucas'], ('user', 'filename please'))
    found = lambda text: titles(call(RHSessionList, users['lucas'], sessions_module, monkeypatch,  # noqa: E731
                                     args={'search': text})[1])
    assert found('100%') == ['Budget up 100% this year']
    assert found('file_name') == ['file_name please']
    assert found('%') == ['Budget up 100% this year']


def test_pages_and_total_count_the_same_conversations(db, users, monkeypatch):
    for n in range(4):
        session_of(db, users['lucas'], ('user', f'budget {n}'), age_minutes=n)
    session_of(db, users['lucas'], ('user', 'agenda'), age_minutes=10)
    session_of(db, users['lucas'])  # nothing said in it: not listed, not counted
    _, body = call(RHSessionList, users['lucas'], sessions_module, monkeypatch, args={'search': 'budget'})
    assert body['total'] == 4
    _, first = call(RHSessionList, users['lucas'], sessions_module, monkeypatch, args={'limit': '3'})
    _, second = call(RHSessionList, users['lucas'], sessions_module, monkeypatch, args={'limit': '3', 'offset': '3'})
    assert first['total'] == second['total'] == 5
    assert titles(first) + titles(second) == ['budget 0', 'budget 1', 'budget 2', 'budget 3', 'agenda']


def test_a_conversation_opened_before_its_first_question_starts_on_that_questions_page(db, users, monkeypatch, queued):
    # (review, PR #5: the panel opens it with PUT, and POST /chat then found it without an event)
    thread = uuid4()
    call(RHSessionOpen, users['lucas'], sessions_module, monkeypatch, json={'first_message': 'hi'},
         view_args={'session_id': str(thread)})
    monkeypatch.setattr('indico_assistant.services.chat.service.ChatService._validate_event_access',
                        lambda self, user, event_id: None)
    call(RHChat, users['lucas'], chat_module, monkeypatch, json={'message': 'hi', 'session_id': str(thread),
                                                                'event_id': 351})
    assert ChatSession.query.get(thread).event_id == 351


def test_each_answer_carries_only_the_callers_feedback(db, users, monkeypatch):
    chat = session_of(db, users['lucas'], ('user', 'q'), ('assistant', 'a'))
    answer = ChatMessage.query.filter_by(session_id=chat.id, role='assistant').one()
    mine = FeedbackEntry(message_id=answer.id, user_id=users['lucas'].id, feedback_type='thumbs_up', value='true')
    db.session.add_all([mine, FeedbackEntry(message_id=answer.id, user_id=users['makoto'].id,
                                            feedback_type='thumbs_down', value='true')])
    db.session.flush()
    _, body = call(RHSessionDetail, users['lucas'], sessions_module, monkeypatch, view_args={'session_id': str(chat.id)})
    assert body['messages'][1]['feedback'] == {'id': str(mine.id), 'value': 1, 'comment': None}
    assert body['messages'][0].get('feedback') is None



# --- US3: Past Chats search, and two users on one browser (T037, SC-005) ----------------------------------

def titles(body):
    return [item['title'] for item in body['sessions']]


def test_search_finds_words_in_the_title_or_the_messages(db, users, monkeypatch):
    session_of(db, users['lucas'], ('user', 'move the weekly sync'), title='Weekly sync')
    session_of(db, users['lucas'], ('user', 'who speaks?'), ('assistant', 'The Q4 BUDGET review has two talks'))
    session_of(db, users['lucas'], ('user', 'lunch plans'))
    _, body = call(RHSessionList, users['lucas'], sessions_module, monkeypatch, args={'search': 'budget'})
    assert titles(body) == ['who speaks?']  # case-insensitive, in an answer too
    _, body = call(RHSessionList, users['lucas'], sessions_module, monkeypatch, args={'search': 'WEEKLY'})
    assert titles(body) == ['Weekly sync']
    _, body = call(RHSessionList, users['lucas'], sessions_module, monkeypatch, args={'search': 'weekly lunch'})
    assert titles(body) == []  # every word must match


def test_search_never_reaches_someone_elses_conversations(db, users, monkeypatch):
    session_of(db, users['makoto'], ('user', 'the secret budget'))
    session_of(db, users['lucas'], ('user', 'my budget'))
    _, body = call(RHSessionList, users['lucas'], sessions_module, monkeypatch, args={'search': 'budget'})
    assert titles(body) == ['my budget']


def test_a_remembered_conversation_id_is_worthless_to_another_user(db, users, monkeypatch, queued):
    # SC-005: the browser keeps the conversation id per user, but even sent on purpose, it opens nothing
    lucas_chat = session_of(db, users['lucas'], ('user', 'mine'))
    view = {'session_id': str(lucas_chat.id)}
    assert call(RHSessionDetail, users['makoto'], sessions_module, monkeypatch, view_args=view)[0] == 403
    assert call(RHSessionDelete, users['makoto'], sessions_module, monkeypatch, view_args=view)[0] == 403
    assert call(RHChat, users['makoto'], chat_module, monkeypatch,
                json={'message': 'hi', 'session_id': str(lucas_chat.id)})[0] == 403
    _, body = call(RHSessionList, users['makoto'], sessions_module, monkeypatch)
    assert str(lucas_chat.id) not in [item['session_id'] for item in body['sessions']]
    assert ChatSession.query.get(lucas_chat.id) is not None
    assert ChatMessage.query.filter_by(session_id=lucas_chat.id).count() == 1



# --- US4: rename and delete (T042) ------------------------------------------------------------------------

@pytest.mark.parametrize(('title', 'status', 'stored'), [
    ('  Weekly sync  ', 200, 'Weekly sync'), ('x' * 200, 200, 'x' * 200),
    ('   ', 422, None), ('x' * 201, 422, None), (None, 422, None),
])
def test_a_conversation_can_be_renamed(db, users, monkeypatch, title, status, stored):
    chat = session_of(db, users['lucas'], ('user', 'move the sync'), age_minutes=90)
    before = chat.updated_at
    got, body = call(RHSessionRename, users['lucas'], sessions_module, monkeypatch,
                     json={'title': title}, view_args={'session_id': str(chat.id)})
    db.session.expire_all()
    chat = ChatSession.query.get(chat.id)
    assert got == status and chat.title == stored
    assert chat.updated_at == before  # a rename is not activity: its place in the sidebar stays
    if status == 200:
        assert body['title'] == stored and body['session_id'] == str(chat.id)


def test_only_the_owner_renames(db, users, monkeypatch):
    chat = session_of(db, users['lucas'], ('user', 'mine'))
    got, _ = call(RHSessionRename, users['makoto'], sessions_module, monkeypatch,
                  json={'title': 'hijacked'}, view_args={'session_id': str(chat.id)})
    assert got == 403 and chat.title is None
    got, _ = call(RHSessionRename, users['lucas'], sessions_module, monkeypatch,
                  json={'title': 'x'}, view_args={'session_id': str(uuid4())})
    assert got == 404


def test_deleting_keeps_the_conversations_action_plans(db, users, monkeypatch):
    from indico_assistant.models import ActionPlan
    from indico_assistant.services.actions import executor
    chat = session_of(db, users['lucas'], ('user', 'make a meeting'))
    plan, _ = executor.create_plan(users['lucas'], chat.id, steps=[], summary='Make it')
    got, _ = call(RHSessionDelete, users['lucas'], sessions_module, monkeypatch, view_args={'session_id': str(chat.id)})
    db.session.expire_all()
    assert got in (200, 204) and ChatSession.query.get(chat.id) is None
    assert ActionPlan.query.get(plan.id).session_id is None  # the audit trail stays (spec 019)



def test_the_panel_opens_a_conversation_before_its_first_question_is_stored(db, users, monkeypatch):
    # Chainlit lists Past Chats and opens /thread/<id> on a first message, before the chat API stores it:
    # the conversation exists (and is listed) from then on
    thread_id = uuid4()
    view = {'session_id': str(thread_id)}
    status, body = call(RHSessionOpen, users['lucas'], sessions_module, monkeypatch, view_args=view,
                        json={'first_message': 'Who are the speakers of the Q4 budget review and when do they talk?'})
    assert status == 201 and body['title'] == 'Who are the speakers of the Q4 budget review and when do…'
    _, listed = call(RHSessionList, users['lucas'], sessions_module, monkeypatch)
    assert str(thread_id) in [item['session_id'] for item in listed['sessions']]
    status, _ = call(RHSessionOpen, users['lucas'], sessions_module, monkeypatch, view_args=view, json={'first_message': 'x'})
    assert status == 200 and ChatSession.query.get(thread_id).title.startswith('Who are')  # unchanged
    assert call(RHSessionOpen, users['makoto'], sessions_module, monkeypatch, view_args=view, json={})[0] == 403



def test_creating_under_an_id_twice_is_harmless(db, users):
    # the first question and Chainlit's naming of the thread create it at the same moment (seen live: a 500)
    thread_id = uuid4()
    first = get_session_manager().create_session(users['lucas'].id, None, session_id=thread_id)
    again = get_session_manager().create_session(users['lucas'].id, 351, session_id=thread_id)
    assert first.id == again.id == thread_id and again.event_id is None  # the first one stands
    theirs = get_session_manager().create_session(users['makoto'].id, None, session_id=thread_id)
    assert theirs.user_id == users['lucas'].id  # never taken over (callers refuse it: 403)


# --- Phase 7: the panel's thumbs are Indico feedback (T046) -------------------------------------------------

def test_an_answer_is_stored_under_the_id_the_panel_asked_for(db, users, monkeypatch, queued):
    # Chainlit's thumbs vote on the answer's run: the answer is stored under the run's id (T047)
    run_id = uuid4()
    _, body = call(RHChat, users['lucas'], chat_module, monkeypatch, json={'message': 'q', 'answer_id': str(run_id)})
    question = ChatMessage.query.filter_by(session_id=body['session_id'], role='user').one()
    manager = get_session_manager()
    assert manager.answer_id_of(question.id) == run_id
    answer = manager.add_assistant_message(ChatSession.query.get(body['session_id']), 'a',
                                           message_id=manager.answer_id_of(question.id))
    assert answer.id == run_id
    assert manager.answer_id_of(question.id) is None  # an id already in use is not taken twice


def test_a_thumb_can_be_switched_and_taken_back(db, users, monkeypatch):
    chat = session_of(db, users['lucas'], ('user', 'q'), ('assistant', 'a'))
    answer = ChatMessage.query.filter_by(session_id=chat.id, role='assistant').one()
    vote = lambda kind, value=True: call(RHFeedback, users['lucas'], feedback_module, monkeypatch,  # noqa: E731
                                         json={'message_id': str(answer.id), 'feedback_type': kind, 'value': value})
    detail = lambda: call(RHSessionDetail, users['lucas'], sessions_module, monkeypatch,  # noqa: E731
                          view_args={'session_id': str(chat.id)})[1]['messages'][1].get('feedback')
    vote('thumbs_down')
    vote('comment', 'wrong meeting')
    status, body = vote('thumbs_up')  # a switch replaces the vote, the comment stays
    assert status == 201 and detail() == {'id': body['feedback_id'], 'value': 1, 'comment': 'wrong meeting'}

    # someone else cannot take it back, and learns nothing about it
    status, _ = call(RHFeedbackDelete, users['makoto'], feedback_module, monkeypatch,
                     view_args={'feedback_id': body['feedback_id']})
    assert status == 404 and detail() is not None
    status, _ = call(RHFeedbackDelete, users['lucas'], feedback_module, monkeypatch,
                     view_args={'feedback_id': body['feedback_id']})
    assert status == 204 and detail() is None
    assert FeedbackEntry.query.filter_by(message_id=answer.id).count() == 0  # its comment went with it


def test_a_vote_and_its_comment_are_kept_together(db, users, monkeypatch):
    # (review, PR #5: sent apart, a failed comment's rollback deleted the user's earlier comment too)
    chat = session_of(db, users['lucas'], ('user', 'q'), ('assistant', 'a'))
    answer = ChatMessage.query.filter_by(session_id=chat.id, role='assistant').one()
    status, _ = call(RHFeedback, users['lucas'], feedback_module, monkeypatch,
                     json={'message_id': str(answer.id), 'feedback_type': 'thumbs_down', 'value': True,
                           'comment': ' wrong meeting '})
    kinds = {e.feedback_type: e.value for e in FeedbackEntry.query.filter_by(message_id=answer.id)}
    assert status == 201 and kinds == {'thumbs_down': 'true', 'comment': 'wrong meeting'}


def test_a_conversation_whose_first_question_was_refused_drops_out(db, users, monkeypatch):
    # (review, PR #5: the panel opens it with a title before the question; a refused question left it listed)
    fresh = session_of(db, users['lucas'], title='Who speaks?')
    stale = session_of(db, users['lucas'], title='Refused question')
    stale.created_at = stale.created_at - timedelta(minutes=10)
    db.session.flush()
    _, body = call(RHSessionList, users['lucas'], sessions_module, monkeypatch)
    listed = [s['session_id'] for s in body['sessions']]
    assert str(fresh.id) in listed and str(stale.id) not in listed
