"""Suggesting a time (US8): free slots for the user and the named people, from what Indico knows, with the
sources said and the people whose availability is unknown named."""

from datetime import date, datetime, timedelta

import pytest
import pytz

from indico.modules.categories.models.categories import EventCreationMode

from indico_assistant.services.actions import resolve
from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.actions.resolve import Guest, suggest_times
from indico_assistant.services.llm.models.plan import PlanDraft


TZ = pytz.timezone('Europe/Zurich')
MONDAY = date(2026, 10, 5)


@pytest.fixture(autouse=True)
def frozen(monkeypatch, people):
    # "now" is the Sunday before, 20:00 local; the user works in Zurich time
    now = TZ.localize(datetime(2026, 10, 4, 20, 0))
    monkeypatch.setattr(resolve, 'now_utc', lambda: now.astimezone(pytz.utc))
    monkeypatch.setattr(resolve, 'local_today', lambda user: now.date())
    people['manager'].settings.set('timezone', 'Europe/Zurich')


def busy(create_event, person, day, start, end, title='Busy'):
    return create_event(title=title, creator=person, creator_has_privileges=True, timezone='Europe/Zurich',
                        start_dt=TZ.localize(datetime.combine(day, start)),
                        end_dt=TZ.localize(datetime.combine(day, end)))


def test_free_times_avoid_everyones_meetings(people, create_event):
    from datetime import time
    lucas, makoto = people['manager'], people['makoto']
    busy(create_event, lucas, MONDAY, time(9), time(11))  # Lucas: Monday morning
    busy(create_event, makoto, MONDAY, time(11), time(12, 30))  # Makoto: late Monday morning
    busy(create_event, makoto, MONDAY + timedelta(days=1), time(8), time(18))  # Makoto: all Tuesday
    with acting_as(lucas):
        free, sources, unknown = suggest_times(lucas, [makoto], 30)
    local = [t.astimezone(TZ) for t in free]
    assert [(t.date(), t.strftime('%H:%M')) for t in local] == [
        (MONDAY, '12:30'), (MONDAY + timedelta(days=2), '09:00'), (MONDAY + timedelta(days=3), '09:00')]
    assert 'Indico' in sources[0] and unknown == []


def test_people_indico_cannot_see_are_named(people):
    guest = Guest(first_name='Kaori', last_name='Ito', email='kaori@example.org')
    with acting_as(people['manager']):
        _, _, unknown = suggest_times(people['manager'], [guest], 30)
    assert unknown == ['Kaori Ito']  # never assumed free (US8 AS-3)


def test_outlook_is_mentioned_only_when_enabled(people):
    with acting_as(people['manager']):
        _, sources, _ = suggest_times(people['manager'], [], 30, settings={'actions_outlook_freebusy': True})
    assert len(sources) == 2 and 'Outlook' in sources[1]


def test_a_request_without_a_time_offers_choices(people, create_category):
    lucas = people['manager']
    category = create_category(title='Meetings', event_creation_mode=EventCreationMode.restricted)
    category.update_principal(lucas, permissions={'create'})
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'create_meeting', 'category': 'Meetings', 'people': ['Makoto'],
         'when': {'date': None, 'time': None, 'duration_minutes': 30}}]})
    with acting_as(lucas):
        result = resolve.draft_to_plan(draft, lucas, chat_session_id=None)
    (question,) = result.questions
    assert question['id'] == 'time' and question['kind'] == 'choice' and len(question['choices']) == 3
    assert 'These times are free' in question['text'] and 'Indico' in question['text']

    from types import SimpleNamespace

    from indico_assistant.services.actions.planner import answered_draft
    open_plan = SimpleNamespace(draft=draft.model_dump(mode='json'), questions=result.questions)
    picked = answered_draft(open_plan, question['choices'][1]['label']).steps[0].when
    assert (picked.date, picked.time) == (question['choices'][1]['value'][:10], question['choices'][1]['value'][11:16])


def test_this_week_and_next_week():
    from indico_assistant.services.actions.resolve import week_days
    wednesday = date(2026, 9, 30)
    assert week_days('this week', wednesday) == [date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)]
    assert week_days('next week', wednesday) == [date(2026, 10, 5) + timedelta(days=i) for i in range(5)]
    assert week_days('tomorrow', wednesday) is None
    sunday = date(2026, 9, 27)  # seen live: nothing left of this week
    assert week_days('this week', sunday) == [date(2026, 9, 28) + timedelta(days=i) for i in range(5)]


def test_the_week_the_user_said_is_kept():
    from indico_assistant.services.actions.planner import _only_what_the_user_said
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'create_meeting', 'when': {'date': '2026-09-30', 'time': None}}]})  # the model picked a day
    assert _only_what_the_user_said(draft, 'Set up 30 minutes with Makoto this week').steps[0].when.date == 'this week'
