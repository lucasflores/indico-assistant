"""Choosing the category (US3): only allowed ones, ranked with a reason; proposing where only that is
allowed; names matched; and who to ask when there is nowhere to create."""

from datetime import timedelta

import pytest

from indico.modules.categories.models.categories import EventCreationMode
from indico.modules.events.settings import unlisted_events_settings
from indico.util.date_time import now_utc

from indico_assistant.services.actions import resolve
from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.llm.models.plan import PlanDraft


@pytest.fixture
def cats(create_category, people):
    lucas = people['manager']
    engineering = create_category(title='Engineering', event_creation_mode=EventCreationMode.restricted)
    social = create_category(title='Social', event_creation_mode=EventCreationMode.restricted)
    board = create_category(title='Board', event_creation_mode=EventCreationMode.moderated)  # propose only
    create_category(title='Closed', event_creation_mode=EventCreationMode.restricted)
    for category in (engineering, social):
        category.update_principal(lucas, permissions={'create'})
    return {'engineering': engineering, 'social': social, 'board': board}


def plan(user, message='Set up a meeting tomorrow at 10', **meeting):
    step = {'action': 'create_meeting', 'when': {'date': 'tomorrow', 'time': '10:00'}, **meeting}
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [step]})
    with acting_as(user):
        return resolve.draft_to_plan(draft, user, chat_session_id=None, topic=message)


def choices(result):
    (question,) = [q for q in result.questions if q['id'] == 'category']
    return question['choices']


def test_only_allowed_categories_and_propose_only_when_unlisted_events_are_on(people, cats):
    lucas = people['manager']
    assert [c['label'] for c in choices(plan(lucas))] == ['Home » Engineering', 'Home » Social']
    unlisted_events_settings.set('enabled', True)
    labelled = {c['label']: c['note'] for c in choices(plan(lucas))}
    assert labelled == {'Home » Engineering': None, 'Home » Social': None,
                        'Home » Board': 'propose (needs approval)'}


def test_recent_activity_decides_the_suggestion(people, cats, create_event):
    lucas = people['manager']
    for day in (10, 40, 70):
        create_event(title=f'Team sync {day}', category=cats['social'], creator=lucas,
                             creator_has_privileges=True,
                             start_dt=now_utc() - timedelta(days=day), end_dt=now_utc() - timedelta(days=day, hours=-1))
    first, second = choices(plan(lucas))
    assert first['label'] == 'Home » Social'  # ranked first
    assert first['note'] == 'suggested: 3 of your meetings in the last year are here'
    assert second['note'] is None


def test_the_chat_topic_breaks_ties(people, cats, create_event, monkeypatch):
    lucas = people['manager']
    create_event(title='Q3 budget review', category=cats['engineering'], creator=lucas, creator_has_privileges=True,
                 start_dt=now_utc() - timedelta(days=30), end_dt=now_utc() - timedelta(days=30, hours=-1))
    create_event(title='Summer party', category=cats['social'], creator=lucas, creator_has_privileges=True,
                 start_dt=now_utc() - timedelta(days=30), end_dt=now_utc() - timedelta(days=30, hours=-1))
    vectors = {'Q4 budget review meeting': [1, 0], 'Q3 budget review': [0.95, 0.3], 'Summer party': [0, 1]}
    monkeypatch.setattr(resolve, '_embed', lambda texts: [vectors.get(t, [0, 0]) for t in texts])
    first = choices(plan(lucas, message='Q4 budget review meeting'))[0]
    assert first['label'] == 'Home » Engineering'
    assert first['note'] == 'suggested: 1 of your meetings in the last year is here, like “Q3 budget review”'


@pytest.mark.parametrize(('said', 'expected'), [('Engineering', 'Home » Engineering'),
                                                ('home » social', 'Home » Social'), ('social', 'Home » Social')])
def test_a_named_category_is_matched(people, cats, said, expected):
    result = plan(people['manager'], category=said)
    assert not [q for q in result.questions if q['id'] == 'category']
    assert expected in result.summary


def test_an_unknown_name_offers_the_closest(people, cats):
    result = plan(people['manager'], category='Enginering')
    assert choices(result)[0]['label'] == 'Home » Engineering'
    assert 'Enginering' in [q for q in result.questions if q['id'] == 'category'][0]['text']


def test_choosing_a_propose_only_category_proposes(people, cats):
    unlisted_events_settings.set('enabled', True)
    result = plan(people['manager'], category='Board')
    assert result.steps[0]['action'] == 'propose_event'
    assert 'needs approval' in result.summary


def test_nowhere_to_create_says_who_to_ask(people, cats, create_user):
    from indico.modules.categories import Category
    root_manager = create_user(40, first_name='Rita', last_name='Root', email='rita@aithoth.com')
    Category.get_root().update_principal(root_manager, full_access=True)
    result = plan(people['stranger'])
    assert result.refusal and 'Rita Root <rita@aithoth.com>' in result.refusal and not result.steps


def test_propose_only_while_unlisted_events_are_off_explains_why(people, cats):
    stranger = people['stranger']
    cats['board'].update_principal(stranger, read_access=True)  # the board is moderated: they may propose
    result = plan(stranger)
    assert 'Home » Board' in result.refusal and 'unlisted events' in result.refusal


def test_part_of_a_name_is_offered_not_picked(people, cats):
    # seen in the eval: "in Science" picked "Nothing Science"
    result = plan(people['manager'], category='Engin')
    assert choices(result)[0]['label'] == 'Home » Engineering'


@pytest.mark.parametrize(('name', 'said', 'named'), [
    ('HR', 'Set up a meeting in HR tomorrow', True),  # (code review, PR #3) no 4-letter word in the name
    ('IT', 'Set up a meeting tomorrow, make it 30 minutes', False),  # "it" is not "IT"
    ('R&D', 'Set up a meeting in R&D tomorrow', True),
])
def test_short_category_names_can_be_named(name, said, named):
    from indico_assistant.services.actions.planner import _only_what_the_user_asked_for
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'create_meeting', 'category': name, 'when': {}}]})
    assert (_only_what_the_user_asked_for(draft, [said]).steps[0].category == name) is named
