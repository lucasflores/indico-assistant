""""This event" is the page each message is sent from (spec 020 US2, R8): the page line the model gets, and
the page an old message (from before spec 020) falls back to."""

from indico.core.db.sqlalchemy.protection import ProtectionMode

from indico_assistant.models import ChatMessage, ChatSession
from indico_assistant.services.chat.context_builder import ContextBuilder
from indico_assistant.services.chat.session_manager import get_session_manager


def test_the_model_is_told_which_page_the_user_is_on(db, dummy_user, create_event):
    meeting = create_event(title='Sync with Makoto')
    note = ContextBuilder().page_note(meeting.id, dummy_user)
    assert note['role'] == 'system' and f'event {meeting.id} now' in note['content'] and ':event_id' in note['content']
    # the id only (seen live: a title made the SQL generator search for it by keyword, and its namesakes)
    assert 'Sync with Makoto' not in note['content']
    assert 'not on an event page' in ContextBuilder().page_note(None, dummy_user)['content']


def test_no_title_from_an_event_the_user_cannot_see(db, dummy_user, create_user, create_event):
    secret = create_event(title='Board only', creator=create_user(80), protection_mode=ProtectionMode.protected)
    note = ContextBuilder().page_note(secret.id, dummy_user)['content']
    assert 'Board only' not in note and f'event {secret.id}' in note


def test_an_old_question_falls_back_to_where_the_conversation_started(db, dummy_user):
    chat = ChatSession(user_id=dummy_user.id, event_id=351)
    db.session.add(chat)
    db.session.flush()
    old = ChatMessage(session_id=chat.id, role='user', content='before spec 020')
    new = ChatMessage(session_id=chat.id, role='user', content='from event 352', metadata_json={'event_id': 352})
    home = ChatMessage(session_id=chat.id, role='user', content='from the home page', metadata_json={'event_id': None})
    db.session.add_all([old, new, home])
    db.session.flush()
    manager = get_session_manager()
    assert manager.page_event_of(old.id, chat.event_id) == 351
    assert manager.page_event_of(new.id, chat.event_id) == 352
    assert manager.page_event_of(home.id, chat.event_id) is None  # a page without an event: no fallback
