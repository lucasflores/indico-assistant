"""Conversations the panel reads back (spec 020, Phase 2): a session made under the browser's id, the job of
an unanswered question, pages walked with a cursor, titles, and the caller's own feedback."""

from datetime import timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

import indico_assistant.controllers.chat as chat_module
import indico_assistant.controllers.sessions as sessions_module
from indico_assistant.controllers.chat import RHChat
from indico_assistant.controllers.sessions import RHSessionDetail, RHSessionList
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
    monkeypatch.setattr(module, 'get_rate_limiter', MagicMock())
    rh = rh_class.__new__(rh_class)
    rh._user = user
    response, status = rh._process()
    return status, response.get_json()


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


def test_an_unanswered_question_reports_its_job(db, users, monkeypatch):
    chat = session_of(db, users['lucas'], ('user', 'first'), ('assistant', 'answer'))
    view = {'session_id': str(chat.id)}
    status, body = call(RHSessionDetail, users['lucas'], sessions_module, monkeypatch, view_args=view)
    assert status == 200 and body.get('pending_job_id') is None
    db.session.add(ChatMessage(session_id=chat.id, role='user', content='second',
                               metadata_json={'job_id': 'job-2', 'event_id': 351}))
    db.session.flush()
    _, body = call(RHSessionDetail, users['lucas'], sessions_module, monkeypatch, view_args=view)
    assert body['pending_job_id'] == 'job-2' and body['title'] == 'first'
    assert body['messages'][-1]['metadata']['event_id'] == 351


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
