"""The offer of the last answer before a question (spec 022, FR-005)."""

from datetime import timedelta

from indico.util.date_time import now_utc

from indico_assistant.models import ChatMessage, ChatSession
from indico_assistant.services.chat.session_manager import SessionManager


def test_the_last_answer_before_the_question(db, dummy_user):
    chat = ChatSession(user_id=dummy_user.id)
    db.session.add(chat)
    db.session.flush()
    start = now_utc()

    def say(role, content, minutes, **metadata):
        message = ChatMessage(session_id=chat.id, role=role, content=content, metadata_json=metadata,
                              created_at=start + timedelta(minutes=minutes))
        db.session.add(message)
        db.session.flush()
        return message

    say("user", "Can you add a Teams meeting?", 0)
    say("assistant", "Yes. Shall I?", 1, route={"route": "knowledge", "offer": "add a Teams meeting"})
    question = say("user", "yes please", 2)
    manager = SessionManager()
    assert manager.offer_before(chat.id, question.id) == "add a Teams meeting"
    say("assistant", "Here is the plan.", 3, route={"route": "change", "offer": None})
    later = say("user", "thanks", 4)
    assert manager.offer_before(chat.id, later.id) is None  # only the last answer counts
    assert manager.offer_before(chat.id, None) is None
