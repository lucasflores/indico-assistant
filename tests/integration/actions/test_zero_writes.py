"""Zero writes without confirmation of the exact plan shown (US2, SC-002), for every write action:
unconfirmed, cancelled, expired, superseded and double-confirmed plans."""

import io
from datetime import timedelta

import pytest
from flask import g

from indico.modules.categories.models.categories import EventCreationMode
from indico.modules.events import Event
from indico.modules.events.contributions.models.contributions import Contribution
from indico.modules.events.reminders.models.reminders import EventReminder
from indico.modules.vc.models.vc_rooms import VCRoom
from indico.modules.attachments.models.attachments import Attachment
from indico.util.date_time import now_utc

from indico_assistant.models import ChatSession
from indico_assistant.services.actions import ACTIONS, executor, uploads


START = (now_utc() + timedelta(days=3)).replace(minute=0, second=0, microsecond=0)


@pytest.fixture
def writable(people, dummy_event, create_category, create_contribution, teams):
    """One valid single-step plan per write action, all for the manager."""
    from indico.modules.events.settings import unlisted_events_settings
    unlisted_events_settings.set('enabled', True)
    category = create_category(title='Meetings', event_creation_mode=EventCreationMode.restricted)
    category.update_principal(people['manager'], permissions={'create'})
    board = create_category(title='Board', event_creation_mode=EventCreationMode.moderated)
    dummy_event.start_dt, dummy_event.end_dt = START, START + timedelta(hours=2)
    return {
        'create_event': {'category_id': category.id, 'title': 'New meeting', 'start_dt': START.isoformat(),
                         'end_dt': (START + timedelta(minutes=30)).isoformat(), 'timezone': 'UTC'},
        'propose_event': {'category_id': board.id, 'title': 'Proposed meeting', 'start_dt': START.isoformat(),
                          'end_dt': (START + timedelta(minutes=30)).isoformat(), 'timezone': 'UTC'},
        'add_contribution': {'event_id': dummy_event.id, 'title': 'Talk', 'start_dt': START.isoformat(),
                             'duration_minutes': 20, 'speakers': [{'user_id': people['makoto'].id}]},
        'add_reminder': {'event_id': dummy_event.id, 'minutes_before': 15, 'recipients': ['x@example.test']},
        'update_event': {'event_id': dummy_event.id, 'title': 'Renamed meeting'},
        'attach_link': {'target_type': 'event', 'target_id': dummy_event.id, 'url': 'https://example.test/doc'},
        'attach_file': {'target_type': 'event', 'target_id': dummy_event.id, 'upload_uuid': str(uploads.store(
            people['manager'], io.BytesIO(b'%PDF-1.4 x'), 'slides.pdf').uuid)},
        'update_contribution': {'contribution_id': create_contribution(dummy_event, 'Old talk').id, 'title': 'New talk'},
        'add_teams_room': {'event_id': dummy_event.id, 'name': 'Sync', 'coorganizer_ids': [people['manager'].id]},
    }


def footprint(fake):
    """Everything a write action could leave behind or change."""
    return (sorted((e.id, e.title, e.start_dt, e.end_dt) for e in Event.query.filter_by(is_deleted=False)),
            sorted((c.id, c.title, c.duration) for c in Contribution.query.filter_by(is_deleted=False)),
            EventReminder.query.count(), VCRoom.query.count(), len(fake.state['events']),
            Attachment.query.filter_by(is_deleted=False).count())


def test_every_write_action_is_covered(writable):
    from indico_assistant.default_settings import WRITE_ACTIONS
    implemented = set(ACTIONS) & set(WRITE_ACTIONS)
    assert implemented == set(writable)  # a new action needs a case here


@pytest.mark.parametrize('action', ['create_event', 'propose_event', 'add_contribution', 'add_reminder', 'add_teams_room', 'update_event', 'update_contribution', 'attach_link', 'attach_file'])
@pytest.mark.parametrize('state', ['unconfirmed', 'cancelled', 'expired', 'superseded'])
def test_nothing_runs_unless_confirmed(db, people, writable, teams, action, state):
    lucas = people['manager']
    _, fake = teams
    chat = ChatSession(user_id=lucas.id)
    db.session.add(chat)
    db.session.flush()
    plan, token = executor.create_plan(lucas, chat.id, summary='x',
                                       steps=[{'n': 1, 'action': action, 'args': writable[action]}])
    before = footprint(fake)
    if state == 'cancelled':
        executor.cancel(plan.id, lucas)
    elif state == 'expired':
        plan.expires_at = now_utc() - timedelta(minutes=1)
    elif state == 'superseded':
        executor.create_plan(lucas, chat.id, summary='y', supersedes=plan,
                             steps=[{'n': 1, 'action': action, 'args': writable[action]}])
    if state != 'unconfirmed':
        assert executor.confirm(plan.id, lucas, token) == 'not_confirmable'
    with pytest.raises(executor.NotConfirmed):
        executor.run(plan.id)
    assert footprint(fake) == before
    assert fake.calls == []  # no Teams call either


@pytest.mark.parametrize('action', ['create_event', 'propose_event', 'add_contribution', 'add_reminder', 'add_teams_room', 'update_event', 'update_contribution', 'attach_link', 'attach_file'])
def test_a_double_confirmation_runs_once(db, people, writable, teams, action):
    lucas = people['manager']
    _, fake = teams
    chat = ChatSession(user_id=lucas.id)
    db.session.add(chat)
    db.session.flush()
    plan, token = executor.create_plan(lucas, chat.id, summary='x',
                                       steps=[{'n': 1, 'action': action, 'args': writable[action]}])
    assert [executor.confirm(plan.id, lucas, token) for _ in range(2)] == ['confirmed', 'not_confirmable']
    before = footprint(fake)
    g.email_queue = []  # as in the Celery task
    assert executor.run(plan.id).status == 'done'
    after = footprint(fake)
    with pytest.raises(executor.NotConfirmed):
        executor.run(plan.id)  # a second worker delivery of the same plan
    assert footprint(fake) == after != before  # it did something, once
