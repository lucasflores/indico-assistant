"""The example request carried out (US1): a meeting with two 20-minute talks, speakers, a reminder and a
Teams meeting, made through Indico's operations as the user; and all or nothing when anything fails (SC-006)."""

from datetime import timedelta

import pytest
from flask import g

from indico.core.db import db
from indico.modules.categories.models.categories import EventCreationMode
from indico.modules.events import Event
from indico.modules.events.reminders.models.reminders import EventReminder
from indico.modules.logs import EventLogEntry
from indico.modules.vc.models.vc_rooms import VCRoom
from indico.util.date_time import now_utc

from indico_assistant.models import ChatSession
from indico_assistant.services import actions
from indico_assistant.services.actions import executor
from indico_assistant.services.actions.base import Action, ActionArgs


@pytest.fixture
def category(create_category, people):
    category = create_category(title='Meetings', event_creation_mode=EventCreationMode.restricted)
    category.update_principal(people['manager'], permissions={'create'})
    return category


def example_steps(category, lucas, makoto, start):
    end = start + timedelta(minutes=40)
    return [
        {'n': 1, 'action': 'create_event', 'args': {'category_id': category.id, 'title': 'Sync with Makoto',
                                                    'start_dt': start.isoformat(), 'end_dt': end.isoformat(),
                                                    'timezone': 'Europe/Zurich'}},
        {'n': 2, 'action': 'add_contribution', 'refs': {'event_id': '$1'},
         'args': {'title': 'Lucas Flores', 'start_dt': start.isoformat(), 'duration_minutes': 20,
                  'speakers': [{'user_id': lucas.id}]}},
        {'n': 3, 'action': 'add_contribution', 'refs': {'event_id': '$1'},
         'args': {'title': 'Makoto Tanaka', 'start_dt': (start + timedelta(minutes=20)).isoformat(),
                  'duration_minutes': 20, 'speakers': [{'user_id': makoto.id}]}},
        {'n': 4, 'action': 'add_reminder', 'refs': {'event_id': '$1'},
         'args': {'minutes_before': 15, 'recipients': [], 'send_to_speakers': True}},
        {'n': 5, 'action': 'add_teams_room', 'refs': {'event_id': '$1'},
         'args': {'name': 'Sync with Makoto', 'coorganizer_ids': [lucas.id, makoto.id]}},
    ]


@pytest.fixture
def run_example(db, category, people, teams):
    lucas, makoto = people['manager'], people['makoto']
    chat = ChatSession(user_id=lucas.id)
    db.session.add(chat)
    db.session.flush()
    start = (now_utc() + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)

    def _run(extra_steps=()):
        steps = example_steps(category, lucas, makoto, start) + list(extra_steps)
        plan, token = executor.create_plan(lucas, chat.id, steps=steps, summary='Create a Teams meeting')
        assert executor.confirm(plan.id, lucas, token) == 'confirmed'
        g.email_queue = []  # as in the Celery task: mail waits for the commit
        return executor.run(plan.id)
    return _run


def meetings():
    return Event.query.filter_by(title='Sync with Makoto', is_deleted=False).all()


def test_the_example_is_created_as_indico_would(run_example, people, teams, category):
    lucas, makoto = people['manager'], people['makoto']
    _, fake = teams
    plan = run_example()
    assert plan.status == 'done', plan.error

    (event,) = meetings()
    assert event.category == category and event.timezone == 'Europe/Zurich' and event.creator == lucas
    assert event.can_manage(lucas)  # the creator manages it, as with the creation dialog
    talks = sorted(event.contributions, key=lambda c: c.start_dt)
    assert [(c.title, c.duration) for c in talks] == [('Lucas Flores', timedelta(minutes=20)),
                                                      ('Makoto Tanaka', timedelta(minutes=20))]
    assert talks[1].start_dt == talks[0].end_dt and talks[1].end_dt == event.end_dt
    assert [[link.person.user for link in c.person_links if link.is_speaker] for c in talks] == [[lucas], [makoto]]

    (reminder,) = EventReminder.query.filter_by(event=event).all()
    assert reminder.send_to_speakers and reminder.event_start_delta == timedelta(minutes=15)
    assert reminder.scheduled_dt == event.start_dt - timedelta(minutes=15) and reminder.creator == lucas

    (room,) = VCRoom.query.filter_by(name='Sync with Makoto').all()
    (meeting,) = fake.state['events'].values()
    assert meeting['attendees'] == ['lucas@aithoth.com', 'makoto@aithoth.com'] and not meeting['cancelled']
    assert room.data['event_id'] == plan.result[4]['created']['graph_event_id']

    logs = EventLogEntry.query.filter_by(event=event).all()
    assert logs and all(entry.user == lucas for entry in logs if entry.user)  # every change is the user's
    assert g.email_queue  # notifications queued, sent by the task once committed


class _Boom(Action):
    name = 'test_boom'

    class Args(ActionArgs):
        pass

    def check(self, user, args):
        return None

    def execute(self, user, args):
        raise RuntimeError('after Teams')


@pytest.mark.parametrize('failure', ['teams_setup', 'after_teams', 'commit'])
def test_a_failure_leaves_nothing_behind(run_example, teams, monkeypatch, failure):
    _, fake = teams
    extra = []
    if failure == 'teams_setup':
        fake.fail_next('update_online_meeting', 403, 'Forbidden', 'No application access policy found')
    elif failure == 'after_teams':
        monkeypatch.setitem(actions.ACTIONS, 'test_boom', _Boom())
        extra = [{'n': 6, 'action': 'test_boom', 'args': {}}]
    elif failure == 'commit':
        calls = []
        flush = db.session.flush

        def commit():
            calls.append(1)
            if len(calls) == 2:  # the plan's own commit (the first marks it running)
                raise RuntimeError('database went away')
            flush()
        monkeypatch.setattr(db.session, 'commit', commit)

    rollbacks = []
    monkeypatch.setattr(db.session, 'rollback', lambda: rollbacks.append(1))  # (a no-op in Indico's tests anyway)
    plan = run_example(extra)
    assert plan.status == 'failed' and rollbacks
    if failure != 'commit':
        # a failed commit is undone by that real rollback; in tests the steps' savepoint is already released
        assert meetings() == [] and VCRoom.query.filter_by(name='Sync with Makoto').count() == 0
    assert all(meeting['cancelled'] for meeting in fake.state['events'].values())  # no live Teams meeting
    assert g.email_queue == []  # no mail about a meeting that does not exist
