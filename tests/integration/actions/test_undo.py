"""Undo (US7): a plan the user confirmed in the last 24 hours, from any chat, reversed after confirmation."""

from datetime import timedelta

import pytest
from flask import g

from indico.modules.categories.models.categories import EventCreationMode
from indico.modules.events import Event
from indico.util.date_time import now_utc

from indico_assistant.models import ChatSession
from indico_assistant.services.actions import executor, resolve
from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.llm.models.plan import PlanDraft


START = (now_utc() + timedelta(days=2)).replace(hour=14, minute=0, second=0, microsecond=0)


@pytest.fixture
def made(db, people, create_category, teams):
    """(chat, plan, event): a Teams meeting with one talk, created by a carried-out plan."""
    lucas = people['manager']
    category = create_category(title='Meetings', event_creation_mode=EventCreationMode.restricted)
    category.update_principal(lucas, permissions={'create'})
    chat = new_chat(db, lucas)
    plan = run(lucas, chat, [
        {'n': 1, 'action': 'create_event', 'args': {'category_id': category.id, 'title': 'Undo me',
                                                    'start_dt': START.isoformat(),
                                                    'end_dt': (START + timedelta(minutes=30)).isoformat(),
                                                    'timezone': 'UTC'}},
        {'n': 2, 'action': 'add_contribution', 'refs': {'event_id': '$1'},
         'args': {'title': 'Talk', 'start_dt': START.isoformat(), 'duration_minutes': 20}},
        {'n': 3, 'action': 'add_teams_room', 'refs': {'event_id': '$1'},
         'args': {'name': 'Undo me', 'coorganizer_ids': [lucas.id]}}])
    return chat, plan, Event.get(plan.result[0]['created']['event_id'])


def new_chat(db, user):
    chat = ChatSession(user_id=user.id)
    db.session.add(chat)
    db.session.flush()
    return chat


def run(user, chat, steps, **kw):
    plan, token = executor.create_plan(user, chat.id, steps=steps, summary=kw.pop('summary', 'Make “Undo me”'), **kw)
    executor.confirm(plan.id, user, token)
    g.email_queue = []
    result = executor.run(plan.id)
    assert result.status == 'done', result.error
    return result


def undo(user, chat, which='last'):
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [{'action': 'undo', 'which': which}]})
    with acting_as(user):
        return resolve.draft_to_plan(draft, user, chat_session_id=chat.id)


def test_undo_that_reverses_the_plan_last_step_first(db, people, made):
    lucas = people['manager']
    chat, plan, event = made
    resolved = undo(lucas, chat)
    assert resolved.questions == [] and resolved.undoes == plan
    # last step first (the fixture's steps have no descriptions, so their action names are shown)
    assert resolved.steps[0]['side_effects'] == ['undo “add_teams_room”', 'undo “add_contribution”',
                                                 'undo “create_event”']
    undo_plan = run(lucas, chat, resolved.steps, undoes=plan, summary=resolved.summary)
    assert event.is_deleted and all(c.is_deleted for c in event.contributions)
    assert g.vc_teams_pending_cancel  # deleting the meeting cancels the Teams meeting after the commit
    assert undo(lucas, chat).refusal  # and it cannot be undone twice
    assert undo_plan.undoes_id == plan.id


def test_from_another_chat_the_plans_are_listed(db, people, made):
    lucas = people['manager']
    chat, plan, _ = made
    other = run(lucas, chat, [{'n': 1, 'action': 'update_event', 'args': {
        'event_id': made[2].id, 'title': 'Undo me (renamed)'}}], summary='Rename “Undo me”')
    resolved = undo(lucas, new_chat(db, lucas))
    (question,) = resolved.questions
    assert [c['value'] for c in question['choices']] == [f'#p{other.id}', f'#p{plan.id}']
    assert undo(lucas, new_chat(db, lucas), which=f'#p{plan.id}').steps[0]['args'] == {'plan_id': str(plan.id)}


def test_undoing_a_change_restores_it_and_says_what_changed_since(db, people, made):
    lucas = people['manager']
    chat, _, event = made
    rename = run(lucas, chat, [{'n': 1, 'action': 'update_event', 'args': {
        'event_id': event.id, 'title': 'Renamed'}}], summary='Rename “Undo me”')
    event.title = 'Renamed again by someone'  # after the plan ran
    resolved = undo(lucas, chat)
    assert resolved.undoes == rename and 'was changed since (title)' in resolved.summary
    run(lucas, chat, resolved.steps, undoes=rename)
    assert event.title == 'Undo me'


def test_never_someone_elses_or_older_than_a_day(db, people, made):
    chat, plan, _ = made
    assert undo(people['stranger'], new_chat(db, people['stranger'])).refusal
    plan.finished_at = now_utc() - timedelta(hours=25)
    assert undo(people['manager'], chat).refusal


def test_a_locked_meeting_is_not_undone(db, people, made):
    # (Copilot review, PR #3) undo is a write like any other: a locked event refuses it
    lucas = people['manager']
    chat, plan, event = made
    resolved = undo(lucas, chat)
    event.is_locked = True  # locked after the undo was planned
    undo_plan, token = executor.create_plan(lucas, chat.id, steps=resolved.steps, summary='undo', undoes=plan)
    executor.confirm(undo_plan.id, lucas, token)
    result = executor.run(undo_plan.id)
    assert result.status == 'refused' and 'locked' in result.error
    assert not event.is_deleted


@pytest.fixture
def existing(db, people, dummy_event, teams):
    """(chat, plan, event): a plan that added a Teams room, a reminder that was too late, and a link to a
    meeting that already existed."""
    lucas = people['manager']
    dummy_event.update_principal(lucas, full_access=True)
    dummy_event.start_dt = now_utc() + timedelta(minutes=5)  # too soon for a 15-minute reminder
    dummy_event.end_dt = dummy_event.start_dt + timedelta(hours=1)
    chat = new_chat(db, lucas)
    plan = run(lucas, chat, [
        {'n': 1, 'action': 'add_reminder', 'args': {'event_id': dummy_event.id, 'minutes_before': 15}},
        {'n': 2, 'action': 'attach_link', 'args': {'target_type': 'event', 'target_id': dummy_event.id,
                                                   'url': 'https://indico.example/agenda', 'title': 'Agenda'}},
        {'n': 3, 'action': 'add_teams_room', 'args': {'event_id': dummy_event.id, 'name': 'Sync',
                                                      'coorganizer_ids': [lucas.id]}}], summary='Add to it')
    assert plan.result[0].get('skipped')  # the reminder
    return chat, plan, dummy_event


def test_undo_removes_a_teams_room_from_a_meeting_that_existed(people, existing):
    # (Copilot Balanced review, PR #3) the room's undo was a no-op; and a skipped reminder crashed the undo
    from indico.modules.vc.models.vc_rooms import VCRoomEventAssociation
    lucas = people['manager']
    chat, plan, event = existing
    assert VCRoomEventAssociation.find_for_event(event).count() == 1
    resolved = undo(lucas, chat)
    undo_plan = run(lucas, chat, resolved.steps, undoes=plan, summary=resolved.summary)
    assert undo_plan.status == 'done' and not event.is_deleted
    assert VCRoomEventAssociation.find_for_event(event).count() == 0
    assert g.vc_teams_pending_cancel  # the Teams meeting is cancelled after the commit
    assert not [a for f in event.attachment_folders for a in f.attachments if not a.is_deleted]


def test_undoing_additions_to_a_locked_meeting_is_refused(people, existing):
    lucas = people['manager']
    chat, plan, event = existing
    resolved = undo(lucas, chat)
    event.is_locked = True
    undo_plan, token = executor.create_plan(lucas, chat.id, steps=resolved.steps, summary='undo', undoes=plan)
    executor.confirm(undo_plan.id, lucas, token)
    assert executor.run(undo_plan.id).status == 'refused'
