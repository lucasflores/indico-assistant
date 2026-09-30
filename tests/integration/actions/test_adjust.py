"""Adjusting meetings (US6): "move it to 3pm", renaming, adding and changing talks; parity with the
event-editing pages; the talks and the Teams meeting move with the event."""

from datetime import timedelta

import pytest
from flask import g

from indico.modules.categories.models.categories import EventCreationMode
from indico.modules.events.management.controllers.settings import RHEditEventData, RHEditEventDates
from indico.modules.events.timetable.controllers.legacy import RHLegacyTimetableEditEntry
from indico.util.date_time import now_utc

from indico_assistant.models import ChatSession
from indico_assistant.services.actions import ACTIONS, executor, resolve
from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.llm.models.plan import PlanDraft


ROLES = ['admin', 'manager', 'contributions_manager', 'submitter', 'stranger']
START = (now_utc() + timedelta(days=2)).replace(hour=14, minute=0, second=0, microsecond=0)


@pytest.mark.parametrize('role', ROLES)
@pytest.mark.parametrize('locked', [False, True])
def test_update_event_parity(page_allows, action_allows, people, dummy_event, role, locked):
    dummy_event.is_locked = locked
    user = people[role]
    ours = action_allows(ACTIONS['update_event'], user, event_id=dummy_event.id, title='Renamed')
    assert ours == page_allows(RHEditEventData, user, event=dummy_event) == \
        page_allows(RHEditEventDates, user, event=dummy_event), role


@pytest.mark.parametrize('role', ROLES)
def test_update_contribution_parity(page_allows, action_allows, people, dummy_event, create_contribution, role):
    talk = create_contribution(dummy_event, 'Talk')
    user = people[role]
    assert action_allows(ACTIONS['update_contribution'], user, contribution_id=talk.id, title='New') == \
        page_allows(RHLegacyTimetableEditEntry, user, event=dummy_event, session=None), role


@pytest.fixture
def meeting(db, people, create_category, teams):
    """A meeting made in a chat by a carried-out plan: two talks and a Teams room, 14:00-14:40."""
    lucas, makoto = people['manager'], people['makoto']
    lucas.settings.set('timezone', 'UTC')
    category = create_category(title='Meetings', event_creation_mode=EventCreationMode.restricted)
    category.update_principal(lucas, permissions={'create'})
    chat = ChatSession(user_id=lucas.id)
    db.session.add(chat)
    db.session.flush()
    steps = [
        {'n': 1, 'action': 'create_event', 'args': {'category_id': category.id, 'title': 'Weekly sync',
                                                    'start_dt': START.isoformat(),
                                                    'end_dt': (START + timedelta(minutes=40)).isoformat(),
                                                    'timezone': 'UTC'}},
        *({'n': n, 'action': 'add_contribution', 'refs': {'event_id': '$1'},
           'args': {'title': who.full_name, 'start_dt': (START + timedelta(minutes=20 * (n - 2))).isoformat(),
                    'duration_minutes': 20, 'speakers': [{'user_id': who.id}]}}
          for n, who in ((2, lucas), (3, makoto))),
        {'n': 4, 'action': 'add_teams_room', 'refs': {'event_id': '$1'},
         'args': {'name': 'Weekly sync', 'coorganizer_ids': [lucas.id]}},
    ]
    run(lucas, chat, steps)
    return chat, executor.made_in_chat(chat.id) if hasattr(executor, 'made_in_chat') else resolve.made_in_chat(chat.id)


def run(user, chat, steps):
    plan, token = executor.create_plan(user, chat.id, steps=steps, summary='x')
    executor.confirm(plan.id, user, token)
    g.email_queue = []
    result = executor.run(plan.id)
    assert result.status == 'done', result.error
    return result


def change(user, chat, **what):
    step = {'action': 'change_meeting', **what}
    with acting_as(user):
        return resolve.draft_to_plan(PlanDraft.model_validate({'decision': 'new_request', 'steps': [step]}), user,
                                     chat_session_id=chat.id)


def test_move_it_to_3pm_moves_talks_and_teams(people, meeting, teams):
    lucas = people['manager']
    chat, event = meeting
    _, fake = teams
    plan = change(lucas, chat, meeting='it', move_to={'time': '3pm'})
    assert plan.questions == [] and [s['action'] for s in plan.steps] == ['update_event']
    assert 'Its 2 talks move with it' in plan.steps[0]['side_effects']
    assert 'The Teams meeting moves too' in plan.steps[0]['side_effects']
    run(lucas, chat, plan.steps)
    assert (event.start_dt, event.end_dt) == (START + timedelta(hours=1), START + timedelta(hours=1, minutes=40))
    assert sorted(c.start_dt for c in event.contributions) == [START + timedelta(hours=1),
                                                               START + timedelta(hours=1, minutes=20)]
    assert g.vc_teams_pending_move  # vc_teams moves the Teams meeting once this commits


def test_add_a_qa_at_the_end_extends_the_meeting(people, meeting):
    lucas = people['manager']
    chat, event = meeting
    plan = change(lucas, chat, meeting='it', add_slots=[{'title': 'Q&A', 'duration_minutes': 10}])
    assert plan.steps[0]['args']['start_dt'] == (START + timedelta(minutes=40)).isoformat().replace('+00:00', 'Z') \
        or plan.steps[0]['args']['start_dt'].startswith((START + timedelta(minutes=40)).strftime('%Y-%m-%dT%H:%M'))
    assert 'extended to end at 14:50' in plan.summary
    run(lucas, chat, plan.steps)
    assert event.end_dt == START + timedelta(minutes=50) and len(event.contributions) == 3


def test_change_the_speaker_of_the_second_talk(people, meeting, create_user):
    lucas = people['manager']
    chat, event = meeting
    kaori = create_user(70, first_name='Kaori', last_name='Ito', email='kaori@aithoth.com')
    plan = change(lucas, chat, meeting='it', change_slots=[{'which': 'second', 'speaker': 'Kaori'}])
    assert plan.steps[0]['action'] == 'update_contribution'
    run(lucas, chat, plan.steps)
    second = sorted(event.contributions, key=lambda c: c.start_dt)[1]
    assert [link.person.user for link in second.person_links if link.is_speaker] == [kaori]


def test_a_named_meeting_among_several_is_asked(db, people, meeting, create_event, dummy_event):
    lucas = people['manager']
    _, event = meeting
    chat = ChatSession(user_id=lucas.id)  # another chat: no meeting made here
    db.session.add(chat)
    db.session.flush()
    other = create_event(title='Weekly sync (team B)', start_dt=START + timedelta(days=7),
                         end_dt=START + timedelta(days=7, hours=1), creator=lucas, creator_has_privileges=True)
    plan = change(lucas, chat, meeting='weekly sync', title='Weekly sync (renamed)')
    (question,) = plan.questions
    assert sorted(c['value'] for c in question['choices']) == sorted([f'#{event.id}', f'#{other.id}'])
    answered = change(lucas, chat, meeting=f'#{other.id}', title='Weekly sync (renamed)')
    assert answered.steps[0]['args'] == {'event_id': other.id, 'title': 'Weekly sync (renamed)',
                                         'description': None, 'start_dt': None, 'end_dt': None}


def test_someone_elses_meeting_is_refused(people, meeting):
    chat, event = meeting
    assert 'could not find' in change(people['stranger'], chat, meeting='Weekly sync', title='Mine').refusal
    assert 'cannot manage' in change(people['stranger'], chat, meeting=f'#{event.id}', title='Mine').refusal


def test_too_short_for_its_talks_is_refused_at_check(action_allows, people, meeting):
    _, event = meeting
    # moving the start 30 minutes later but keeping the end: the talks would not fit (EventDatesForm)
    assert not action_allows(ACTIONS['update_event'], people['manager'], event_id=event.id,
                             start_dt=START + timedelta(minutes=30))


def test_the_meeting_made_here_wins_over_namesakes(people, meeting, create_event):
    lucas = people['manager']
    chat, event = meeting
    create_event(title='Weekly sync', start_dt=START + timedelta(days=1), end_dt=START + timedelta(days=1, hours=1),
                 creator=lucas, creator_has_privileges=True)
    plan = change(lucas, chat, meeting='Weekly sync', move_to={'time': '3pm'})
    assert plan.questions == [] and plan.steps[0]['args']['event_id'] == event.id


def test_a_move_keeps_the_day_unless_the_user_named_one():
    # seen live: "move it to 3pm" came back from the model with a made-up date
    from indico_assistant.services.actions.planner import _only_what_the_user_said
    draft = lambda: PlanDraft.model_validate({'decision': 'new_request', 'steps': [  # noqa: E731
        {'action': 'change_meeting', 'move_to': {'date': '2026-09-29', 'time': '15:00'}}]})
    assert _only_what_the_user_said(draft(), 'move it to 3pm').steps[0].move_to.date is None
    assert _only_what_the_user_said(draft(), 'move it to Tuesday at 3pm').steps[0].move_to.date == 'tuesday'


@pytest.mark.parametrize(('message', 'model_date', 'used'), [
    ('Create a meeting on Thursday at 2pm', '2026-09-29', 'on thursday'),  # seen live: a Tuesday
    ('set something up next Tuesday', '2026-10-13', 'next tuesday'),
    ('meeting tomorrow at 10', '2026-09-30', 'tomorrow'),
    ('meeting on 2026-10-02 at 10', '2026-10-02', '2026-10-02'),
])
def test_the_users_own_words_decide_the_day(message, model_date, used):
    from indico_assistant.services.actions.planner import _only_what_the_user_said
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'create_meeting', 'when': {'date': model_date, 'time': '14:00'}}]})
    assert _only_what_the_user_said(draft, message).steps[0].when.date == used


@pytest.mark.parametrize(('message', 'used'), [
    ("Move Friday's standup to tomorrow", 'tomorrow'),  # (code review, PR #3) the day that names the meeting
    ("Create a prep meeting tomorrow for Monday's review", 'tomorrow'),
    ('move the Monday sync to next Friday', 'next friday'),
])
def test_the_day_is_the_one_the_meeting_is_for(message, used):
    from indico_assistant.services.actions.planner import _only_what_the_user_said
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'change_meeting', 'move_to': {'date': '2026-09-29', 'time': '15:00'}}]})
    assert _only_what_the_user_said(draft, message).steps[0].move_to.date == used


@pytest.mark.parametrize('message', ['move the follow-up to 3pm', 'move the Q&A/demo to 3pm'])
def test_a_dash_or_slash_is_not_a_date(message):
    from indico_assistant.services.actions.planner import _only_what_the_user_said
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'change_meeting', 'move_to': {'date': '2026-09-29', 'time': '15:00'}}]})
    assert _only_what_the_user_said(draft, message).steps[0].move_to.date is None  # the model's date is dropped


def test_a_revision_keeps_the_day_already_named():
    # "move it to Tuesday 3pm", then "actually make it 4pm": still Tuesday, whatever the model says
    from types import SimpleNamespace

    from indico_assistant.services.actions.planner import _only_what_the_user_said
    open_plan = SimpleNamespace(draft={'steps': [{'action': 'change_meeting',
                                                  'move_to': {'date': 'tuesday', 'time': '3pm'}}]})
    draft = PlanDraft.model_validate({'decision': 'revise', 'steps': [
        {'action': 'change_meeting', 'move_to': {'date': '2026-09-30', 'time': '4pm'}}]})
    assert _only_what_the_user_said(draft, 'actually make it 4pm', open_plan).steps[0].move_to.date == 'tuesday'


def test_undoing_a_speaker_change_restores_every_person(db, people, dummy_event, create_contribution):
    # (code review, PR #3) a guest speaker without an email crashed the undo, and changing the speaker
    # dropped the authors who do not speak
    from indico.modules.events.contributions.models.persons import AuthorType, ContributionPersonLink
    from indico.modules.events.models.persons import EventPerson

    lucas = people['manager']
    dummy_event.update_principal(lucas, full_access=True)
    talk = create_contribution(dummy_event, 'Talk')
    guest = EventPerson(event=dummy_event, first_name='Kaori', last_name='Ito', email='')
    author = EventPerson.for_user(people['stranger'], dummy_event)
    db.session.add_all([guest, author])
    talk.person_links = [
        ContributionPersonLink(person=guest, is_speaker=True, author_type=AuthorType.none, display_order=0),
        ContributionPersonLink(person=author, is_speaker=False, author_type=AuthorType.primary, display_order=1)]
    db.session.flush()

    def people_of(contribution):
        return sorted((link.full_name, link.is_speaker, link.author_type) for link in contribution.person_links)
    original = people_of(talk)
    changed = run(lucas, ChatSession.query.first() or _chat(db, lucas), [
        {'n': 1, 'action': 'update_contribution', 'args': {'contribution_id': talk.id,
                                                           'speakers': [{'user_id': lucas.id}]}}])
    assert (author.full_name, False, AuthorType.primary) in people_of(talk)  # the author stayed
    assert guest.full_name not in [name for name, *_ in people_of(talk)]  # the speaker was replaced
    with acting_as(lucas):
        ACTIONS['update_contribution'].revert(lucas, changed.result[0])
    assert people_of(talk) == original


def _chat(db, user):
    chat = ChatSession(user_id=user.id)
    db.session.add(chat)
    db.session.flush()
    return chat


# spec 022: a Teams meeting and a reminder for a meeting that already exists (the capability list offers them)

@pytest.fixture
def existing(db, people, dummy_event):
    """A meeting the manager did not make in this chat, two days ahead, with no Teams room yet."""
    lucas = people['manager']
    lucas.settings.set('timezone', 'UTC')
    dummy_event.start_dt, dummy_event.end_dt = START, START + timedelta(hours=1)
    chat = ChatSession(user_id=lucas.id)
    db.session.add(chat)
    db.session.flush()
    return chat, dummy_event


def test_a_teams_meeting_for_an_existing_meeting(people, existing, teams):
    from indico.modules.vc.models.vc_rooms import VCRoomEventAssociation

    lucas = people['manager']
    chat, event = existing
    plan = change(lucas, chat, meeting=f'#{event.id}', teams=True)
    assert [s['action'] for s in plan.steps] == ['add_teams_room'] and plan.refusal is None
    assert plan.steps[0]['args'] == {'event_id': event.id, 'name': event.title, 'coorganizer_ids': [lucas.id],
                                     'description': ''}
    run(lucas, chat, plan.steps)
    assert [a.vc_room.type for a in VCRoomEventAssociation.find_for_event(event)] == ['teams']
    again = change(lucas, chat, meeting=f'#{event.id}', teams=True)
    assert again.steps == [] and 'already has a Microsoft Teams meeting' in again.refusal


def test_no_teams_plugin_is_a_reason_not_nothing_to_change(people, existing, monkeypatch):
    from indico_assistant.services.actions import teams as teams_module

    monkeypatch.setattr(teams_module, 'teams_plugin', lambda: None)
    chat, event = existing
    plan = change(people['manager'], chat, meeting=f'#{event.id}', teams=True)
    assert 'Microsoft Teams is not available' in plan.refusal and plan.refusal != resolve.NOTHING_TO_CHANGE


def test_a_reminder_for_an_existing_meeting(people, existing):
    from indico.modules.events.reminders.models.reminders import EventReminder

    lucas = people['manager']
    chat, event = existing
    plan = change(lucas, chat, meeting=f'#{event.id}', reminder={'minutes_before': 1440, 'participants': True})
    (step,) = plan.steps
    assert step['action'] == 'add_reminder' and step['args'] == {
        'event_id': event.id, 'minutes_before': 1440, 'recipients': [], 'send_to_speakers': False,
        'send_to_participants': True}
    assert 'the registered participants' in step['description']
    run(lucas, chat, plan.steps)
    (reminder,) = EventReminder.query.with_parent(event).all()
    assert reminder.send_to_participants and not reminder.send_to_speakers
    assert reminder.scheduled_dt == START - timedelta(days=1)


def test_a_reminder_to_nobody_named_goes_to_speakers_and_participants(people, existing):
    chat, event = existing
    args = change(people['manager'], chat, meeting=f'#{event.id}', reminder={}).steps[0]['args']
    assert (args['minutes_before'], args['send_to_speakers'], args['send_to_participants']) == (15, True, True)
    named = change(people['manager'], chat, meeting=f'#{event.id}', reminder={'people': ['Makoto']}).steps[0]['args']
    assert named['recipients'] == ['makoto@aithoth.com'] and not named['send_to_participants']


def test_a_reminder_at_a_set_time(people, existing):
    chat, event = existing
    tomorrow_9 = (START - timedelta(days=1)).replace(hour=9)
    args = change(people['manager'], chat, meeting=f'#{event.id}',
                  reminder={'at': {'date': (START - timedelta(days=1)).date().isoformat(), 'time': '9am'}}
                  ).steps[0]['args']
    assert args['minutes_before'] == (START - tomorrow_9).total_seconds() // 60


def test_a_reminder_too_late_to_send_is_refused_with_the_reason(people, existing):
    chat, event = existing
    event.start_dt, event.end_dt = now_utc() + timedelta(minutes=10), now_utc() + timedelta(hours=1)
    plan = change(people['manager'], chat, meeting=f'#{event.id}', reminder={'minutes_before': 15})
    assert plan.steps == [] and 'too late for that reminder' in plan.refusal
