"""The conversation's memory (spec 025, T034; real DB for the stored answers and access)."""

from datetime import UTC

from indico.core.db.sqlalchemy.protection import ProtectionMode

from indico_assistant.models.message import ChatMessage
from indico_assistant.services.chat.session_manager import SessionManager
from indico_assistant.services.turn import memory
from indico_assistant.services.turn.memory import Memory


def doc(n, title="f.pdf"):
    return {"kind": "document", "ref": {"attachment_id": n}, "title": title}


def test_positions_count_within_a_kind_in_presentation_order():
    m = Memory()
    m.add("document", {"attachment_id": 7}, "a.pdf")
    m.add("event", {"event_id": 3}, "Budget")
    m.add("document", {"attachment_id": 9}, "b.pdf")
    m.add("document", {"attachment_id": 7}, "a.pdf")  # (presented again: still the first)
    assert [(e["kind"], e["position"]) for e in m.touched] == [("document", 1), ("event", 1), ("document", 2)]
    assert m.documents() == [7, 9]


def test_the_second_one_is_position_2_of_the_last_answers_list(db, dummy_user):
    from datetime import datetime, timedelta

    session = SessionManager().create_session(dummy_user.id)
    t = datetime(2026, 10, 5, 12, tzinfo=UTC)
    old = ChatMessage.create(
        session.id, "assistant", "old", {"touched": [{**doc(1), "position": 1}, {**doc(2), "position": 2}]}
    )
    latest = ChatMessage.create(
        session.id,
        "assistant",
        "two files",
        {"touched": [{**doc(5, "thesis.pdf"), "position": 1}, {**doc(6, "talk.pdf"), "position": 2}]},
    )
    question = ChatMessage.create(session.id, "user", "summarise the second one")
    later = ChatMessage.create(session.id, "assistant", "after", {"touched": [{**doc(8), "position": 1}]})
    for n, message in enumerate((old, latest, question, later)):
        message.created_at = t + timedelta(minutes=n)
    db.session.flush()
    remembered = memory.load(session.id, question.id)
    second = next(e for e in remembered if e["kind"] == "document" and e["position"] == 2)
    assert second["ref"] == {"attachment_id": 6} and remembered[0]["ref"] == {"attachment_id": 5}
    assert {e["ref"]["attachment_id"] for e in remembered} == {1, 2, 5, 6}  # (not 8: after the question)
    assert "document #2: talk.pdf (attachment_id 6)" in Memory(earlier=remembered).render()


def test_a_document_whose_access_was_revoked_is_dropped_on_use(
    db, dummy_user, create_user, create_event, create_attachment
):
    other = create_user(2, email="other@example.test")
    event = create_event(title="Board", protection_mode=ProtectionMode.protected)
    event.update_principal(other, read_access=True)
    attachment = create_attachment(dummy_user, event, title="Minutes")
    db.session.flush()
    entries = [
        {**doc(attachment.id), "position": 1},
        {"kind": "event", "ref": {"event_id": event.id}, "title": "Board", "position": 1},
    ]
    assert memory.usable(other, entries) == entries
    event.update_principal(other, read_access=False)
    db.session.flush()
    assert memory.usable(other, entries) == []  # (the event too, since story 3: FR-021 re-checks every kind)
