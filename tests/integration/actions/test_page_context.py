""""This meeting" in chat actions follows the page too (spec 020 US2, R8): the page the user moved to wins
over the meeting the chat made, unless they made it while already on that page."""

from datetime import timedelta

import pytest

from indico.util.date_time import now_utc

from indico_assistant.models import ChatMessage, ChatSession
from indico_assistant.services.actions import executor, resolve
from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.llm.models.plan import PlanDraft


T0 = now_utc() - timedelta(hours=1)


@pytest.fixture
def world(db, people, create_event):
    lucas = people['manager']
    a, b, made = (create_event(title=t, creator=lucas, creator_has_privileges=True,
                               start_dt=now_utc() + timedelta(days=2), end_dt=now_utc() + timedelta(days=2, hours=1))
                  for t in ('Page A', 'Page B', 'Made in chat'))
    chat = ChatSession(user_id=lucas.id, event_id=a.id)
    db.session.add(chat)
    db.session.flush()
    plan, _ = executor.create_plan(lucas, chat.id, steps=[], summary='Make it')
    plan.status, plan.finished_at = 'done', T0
    plan.result = [{'n': 1, 'action': 'create_event', 'created': {'event_id': made.id}}]
    db.session.flush()
    return lucas, chat, a, b, made


def said(db, chat, event, minutes_after_t0):
    message = ChatMessage(session_id=chat.id, role='user', content='…', metadata_json={'event_id': event.id})
    db.session.add(message)
    db.session.flush()
    message.created_at = T0 + timedelta(minutes=minutes_after_t0)
    db.session.flush()


def test_the_page_of_the_message_is_this_meeting(db, world):
    lucas, chat, a, b, made = world
    said(db, chat, b, 5)  # after the meeting was made, the user moved to B
    assert resolve.meeting_in_view(chat.id, lucas, b.id) == b


def test_the_meeting_just_made_wins_on_the_page_it_was_made_from(db, world):
    lucas, chat, a, b, made = world
    said(db, chat, a, -5)  # on A when the plan made the meeting
    said(db, chat, a, 5)   # "add a talk to it", still on A
    assert resolve.meeting_in_view(chat.id, lucas, a.id) == made


def test_moving_after_it_was_made_hands_it_to_the_page(db, world):
    lucas, chat, a, b, made = world
    said(db, chat, a, -5)
    said(db, chat, b, 5)
    assert resolve.meeting_in_view(chat.id, lucas, b.id) == b
    assert resolve.meeting_in_view(chat.id, lucas, None) == made  # no event page: the one made here


def test_the_page_reaches_a_change_request(db, world):
    lucas, chat, a, b, made = world
    said(db, chat, b, 5)
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'change_meeting', 'meeting': 'this meeting', 'title': 'Renamed'}]})
    with acting_as(lucas):
        plan = resolve.draft_to_plan(draft, lucas, chat_session_id=chat.id, page_event_id=b.id)
    assert plan.steps[0]['args']['event_id'] == b.id
