"""From what the user said to the plan they confirm (US1 acceptance scenarios, research R8-R11)."""

from datetime import timedelta
from uuid import UUID

import pytest

from indico.modules.categories.models.categories import EventCreationMode

from indico_assistant.services.actions import enabled_actions, validate_plan
from indico_assistant.services.actions.context import acting_as, local_today
from indico_assistant.services.actions.resolve import creatable_categories, draft_to_plan, resolve_date
from indico_assistant.services.llm.models.plan import PlanDraft


@pytest.fixture
def categories(create_category, people):
    meetings = create_category(title='Meetings', event_creation_mode=EventCreationMode.restricted)
    other = create_category(title='Other', event_creation_mode=EventCreationMode.restricted)
    create_category(title='Closed', event_creation_mode=EventCreationMode.restricted)  # no rights here
    meetings.update_principal(people['manager'], permissions={'create'})
    other.update_principal(people['manager'], full_access=True)
    return meetings, other


def plan_for(user, **meeting):
    step = {'action': 'create_meeting', 'teams': True, 'when': {'date': 'tomorrow', 'time': '2pm'},
            'people': [{'name': 'Makoto'}],
            'slots': [{'speaker': {'name': 'me'}, 'duration_minutes': 20},
                      {'speaker': {'name': 'Makoto'}, 'duration_minutes': 20}]}
    step.update(meeting)
    draft = PlanDraft.model_validate({'decision': 'new_request', 'reply': 'OK', 'steps': [step]})
    user.settings.set('timezone', 'Europe/Zurich')
    with acting_as(user):
        return draft_to_plan(draft, user, chat_session_id=None)


def test_the_example_with_a_named_category(people, categories, teams):
    lucas, makoto = people['manager'], people['makoto']
    plan = plan_for(lucas, category='Meetings')
    assert plan.questions == []
    assert [s['action'] for s in plan.steps] == ['create_event', 'add_contribution', 'add_contribution',
                                                 'add_reminder', 'add_teams_room']
    event, first, second, reminder, room = (s['args'] for s in plan.steps)
    assert event['category_id'] == categories[0].id and event['timezone'] == 'Europe/Zurich'
    assert event['start_dt'].startswith(f'{local_today(lucas) + timedelta(days=1)}T14:00:00+0')
    assert event['end_dt'][11:16] == '14:40'  # no end given: it fits the two 20-minute talks
    assert (first['speakers'], second['speakers']) == ([{'user_id': lucas.id, 'first_name': '', 'last_name': '', 'email': ''}],
                                                       [{'user_id': makoto.id, 'first_name': '', 'last_name': '', 'email': ''}])
    assert second['start_dt'][11:16] == '14:20'
    assert reminder['send_to_speakers'] and reminder['recipients'] == []  # Makoto is a speaker here
    assert room['coorganizer_ids'] == [lucas.id, makoto.id]
    assert 'Microsoft Teams' in plan.steps[4]['description'] and 'makoto@aithoth.com' in plan.steps[4]['side_effects'][0]
    assert 'Meetings' in plan.summary and '14:00' in plan.summary and 'Europe/Zurich' in plan.summary
    assert validate_plan(plan.steps, enabled_actions({'actions_enabled': True, 'actions_allowed': [
        'create_event', 'add_contribution', 'add_reminder', 'add_teams_room']})) == []


def test_no_category_named_asks_among_the_allowed_ones(people, categories, teams):
    plan = plan_for(people['manager'])
    (question,) = plan.questions
    assert question['id'] == 'category'
    assert sorted(c['label'] for c in question['choices']) == ['Home » Meetings', 'Home » Other']  # not "Closed"
    assert plan.steps[0]['description'].endswith('(once the questions are answered)')


def test_only_categories_the_user_can_create_in(people, categories):
    with acting_as(people['stranger']):
        assert creatable_categories(people['stranger']) == []
    assert plan_for(people['stranger']).refusal.startswith('You cannot create events in any category')


def test_a_longer_meeting_than_asked_is_explained(people, categories, teams):
    plan = plan_for(people['manager'], category='Meetings', when={'date': 'tomorrow', 'time': '14:00',
                                                                  'duration_minutes': 30})
    assert plan.steps[0]['args']['end_dt'][11:16] == '14:40' and 'extended to 40 minutes' in plan.summary


def test_with_makoto_and_no_slots_means_invitee_not_speaker(people, categories, teams):
    plan = plan_for(people['manager'], category='Meetings', slots=[])
    assert [s['action'] for s in plan.steps] == ['create_event', 'add_reminder', 'add_teams_room']
    assert plan.steps[1]['args']['recipients'] == ['makoto@aithoth.com']
    assert not plan.steps[1]['args']['send_to_speakers']


def test_two_makotos_are_asked_about(people, categories, teams, create_user):
    create_user(30, first_name='Makoto', last_name='Sato', email='sato@aithoth.com')
    plan = plan_for(people['manager'], category='Meetings')
    (question,) = plan.questions
    assert question['kind'] == 'choice' and len(question['choices']) == 2  # never picked silently


def test_someone_without_a_teams_account(people, categories, teams):
    _, fake = teams
    fake.add_missing_user('makoto@aithoth.com')
    plan = plan_for(people['manager'], category='Meetings')
    assert plan.steps[-1]['args']['coorganizer_ids'] == [people['manager'].id]
    assert 'Makoto Tanaka will not get a Teams invitation' in plan.summary


def test_relative_dates():
    from datetime import date
    sunday = date(2026, 9, 27)
    assert resolve_date('tomorrow', sunday) == date(2026, 9, 28)
    assert resolve_date('next Tuesday', sunday) == date(2026, 9, 29)
    assert resolve_date('sunday', sunday) == date(2026, 10, 4)
    assert resolve_date('2026-10-02', sunday) == date(2026, 10, 2)
    assert resolve_date('someday', sunday) is None


def test_picking_an_offered_choice_needs_no_llm(people, categories, teams, db):
    from unittest.mock import MagicMock

    from indico_assistant.models import ChatSession
    from indico_assistant.services.actions import planner
    from indico_assistant.services.llm.models.base import LLMResponse

    lucas = people['manager']
    lucas.settings.set('timezone', 'Europe/Zurich')
    chat = ChatSession(user_id=lucas.id)
    db.session.add(chat)
    db.session.flush()
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'create_meeting', 'teams': True, 'when': {'date': 'tomorrow', 'time': '2pm'},
         'slots': [{'speaker': 'me'}, {'speaker': 'Makoto'}]}]})
    llm = MagicMock()
    llm.generate.return_value = LLMResponse(success=True, latency_ms=1, result=draft)
    settings = {'actions_enabled': True, 'actions_allowed': ['create_event', 'add_contribution', 'add_reminder',
                                                             'add_teams_room']}
    with acting_as(lucas):
        first = planner.plan_turn(lucas, chat.id, 'Create a Teams meeting tomorrow at 2pm with Makoto, add both of '
                                 'us as contributors with 20 min slots', [], None, llm=llm, settings=settings)
        assert first.plan['questions'][0]['id'] == 'category' and not first.plan['can_confirm']
        assert first.plan['steps'][0]['description'].startswith('Create event')  # no category yet
        assert 'Sync with Makoto' in first.plan['summary']  # speakers count for the default title

        from indico_assistant.services.actions import executor
        second = planner.plan_turn(lucas, chat.id, 'Home » Meetings', [], executor.open_plan(chat.id), llm=llm,
                                   settings=settings)
    llm.generate.assert_called_once()  # only the first turn used the LLM
    assert second.plan['can_confirm'] and second.plan['questions'] == []
    assert 'Home » Meetings' in second.plan['summary']
    assert executor.open_plan(chat.id).id == UUID(second.plan['id'])


def test_a_slot_each_when_the_model_drops_the_speakers(people, categories, teams):
    plan = plan_for(people['manager'], category='Meetings', slots=[{'duration_minutes': 20}, {'duration_minutes': 20}])
    speakers = [s['args']['speakers'][0]['user_id'] for s in plan.steps if s['action'] == 'add_contribution']
    assert speakers == [people['manager'].id, people['makoto'].id]


def test_teams_unreachable_still_plans_the_meeting(people, categories, teams, monkeypatch):
    # seen in the eval run: without Graph credentials the resolver crashed
    from indico_vc_teams.graph import GraphError

    from indico_assistant.services.actions import teams as teams_action
    def unreachable(user):
        raise GraphError(401, 'auth', 'Could not obtain a Microsoft Graph token')
    monkeypatch.setattr(teams_action, 'tenant_email', unreachable)
    plan = plan_for(people['manager'], category='Meetings')
    assert 'add_teams_room' not in [s['action'] for s in plan.steps] and 'cannot be reached' in plan.summary
    assert plan.steps[0]['action'] == 'create_event'
