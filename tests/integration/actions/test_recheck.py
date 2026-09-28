"""Permissions are checked again when a confirmed plan runs (US2 AS-4, FR-008): if something changed
between showing and confirming, the plan is refused with the reason and nothing is written."""

from datetime import timedelta

import pytest

from indico.modules.categories.models.categories import EventCreationMode
from indico.modules.events import Event
from indico.modules.events.contributions.models.contributions import Contribution
from indico.util.date_time import now_utc

from indico_assistant.models import ChatSession
from indico_assistant.services.actions import executor


START = (now_utc() + timedelta(days=3)).replace(minute=0, second=0, microsecond=0)


@pytest.fixture
def confirmed(db, people):
    def _confirmed(steps):
        chat = ChatSession(user_id=people['manager'].id)
        db.session.add(chat)
        db.session.flush()
        plan, token = executor.create_plan(people['manager'], chat.id, summary='x', steps=steps)
        assert executor.confirm(plan.id, people['manager'], token) == 'confirmed'
        return plan
    return _confirmed


def talk(event, **extra):
    return {'n': 1, 'action': 'add_contribution',
            'args': {'event_id': event.id, 'title': 'Talk', 'start_dt': START.isoformat(), 'duration_minutes': 20}}


@pytest.mark.parametrize(('change', 'reason'), [
    ('lost_management', 'You cannot manage the event'),
    ('locked', 'is locked'),
    ('deleted', 'no longer exists'),
])
def test_event_changes_after_confirmation(confirmed, people, dummy_event, change, reason):
    dummy_event.start_dt, dummy_event.end_dt = START, START + timedelta(hours=2)
    plan = confirmed([talk(dummy_event)])
    if change == 'lost_management':
        dummy_event.update_principal(people['manager'], full_access=False)
    elif change == 'locked':
        dummy_event.is_locked = True
    elif change == 'deleted':
        dummy_event.is_deleted = True
    result = executor.run(plan.id)
    assert result.status == 'refused' and reason in result.error
    assert Contribution.query.filter_by(event_id=dummy_event.id).count() == 0


def test_losing_the_right_to_create_in_the_category(confirmed, people, create_category):
    category = create_category(title='Meetings', event_creation_mode=EventCreationMode.open)
    plan = confirmed([{'n': 1, 'action': 'create_event', 'args': {
        'category_id': category.id, 'title': 'New meeting', 'start_dt': START.isoformat(),
        'end_dt': (START + timedelta(minutes=30)).isoformat(), 'timezone': 'UTC'}}])
    category.event_creation_mode = EventCreationMode.restricted  # a category manager closed it meanwhile
    result = executor.run(plan.id)
    assert result.status == 'refused' and 'cannot create events' in result.error
    assert Event.query.filter_by(title='New meeting').count() == 0


def test_a_blocked_account_cannot_run_its_plan(confirmed, people, dummy_event):
    plan = confirmed([talk(dummy_event)])
    people['manager'].is_blocked = True
    assert executor.run(plan.id).status == 'refused'
