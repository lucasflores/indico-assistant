"""What the assistant says it can do matches what it will do (spec 022, FR-009).

For every action: when ``available()`` gives a reason, the action's own ``check()`` refuses too. On an event page the
two agree exactly; without one, a reason means no event or category the chat can reach allows it.
"""

from datetime import timedelta

import pytest
from indico.modules.categories import Category
from indico.modules.categories.models.categories import EventCreationMode
from indico.util.date_time import now_utc

from indico_assistant.services.actions import ACTIONS
from indico_assistant.services.actions.base import Action
from indico_assistant.services.actions.context import acting_as

ROLES = ['admin', 'manager', 'contributions_manager', 'submitter', 'stranger']
LATER = now_utc() + timedelta(days=2)
ON_THE_EVENT = {  # the arguments of a change on the page's event, for its check
    'update_event': lambda event, talk: {'event_id': event.id, 'title': 'Renamed'},
    'add_contribution': lambda event, talk: {'event_id': event.id, 'title': 'Talk', 'start_dt': LATER,
                                             'duration_minutes': 20},
    'update_contribution': lambda event, talk: {'contribution_id': talk.id, 'title': 'Renamed'},
    'add_reminder': lambda event, talk: {'event_id': event.id, 'minutes_before': 15},
    'attach_link': lambda event, talk: {'target_type': 'event', 'target_id': event.id, 'url': 'https://example.org/a'},
    'add_teams_room': lambda event, talk: {'event_id': event.id, 'name': 'Sync', 'coorganizer_ids': []},
}


def _available(name, user, **scope):
    with acting_as(user):
        return ACTIONS[name].available(user, **scope)


def test_every_action_has_a_summary_and_availability():
    for name, action in ACTIONS.items():
        assert action.summary and action.summary[0].islower(), name  # one plain phrase: "create a meeting (...)"
        assert type(action).available is not Action.available, name


@pytest.mark.parametrize('name', sorted(ON_THE_EVENT))
@pytest.mark.parametrize('role', ROLES)
@pytest.mark.parametrize('locked', [False, True])
def test_on_an_event_it_agrees_with_the_check(action_allows, people, dummy_event, dummy_contribution, teams, name,
                                              role, locked):
    dummy_event.is_locked = locked
    user = people[role]
    reason = _available(name, user, event=dummy_event)
    allowed = action_allows(ACTIONS[name], user, **ON_THE_EVENT[name](dummy_event, dummy_contribution))
    assert (reason is None) == allowed, (role, reason)


@pytest.mark.parametrize('acl', ['everyone', 'only_admins'])
def test_teams_follows_the_plugins_own_list(action_allows, people, dummy_event, teams, acl):
    plugin, _ = teams
    if acl == 'only_admins':
        plugin.settings.acls.set('acl', {people['admin']})
    manager = people['manager']
    assert (_available('add_teams_room', manager, event=dummy_event) is None) == (acl == 'everyone')
    assert (_available('add_teams_room', manager) is None) == (acl == 'everyone')


def test_teams_without_the_plugin(people, dummy_event, monkeypatch):
    from indico_assistant.services.actions import teams as teams_action
    monkeypatch.setattr(teams_action, 'teams_plugin', lambda: None)
    assert _available('add_teams_room', people['admin'], event=dummy_event) == \
        'Microsoft Teams is not available on this Indico'


def test_a_speaker_may_add_material_to_their_own_talk(action_allows, people, dummy_event, dummy_contribution):
    speaker = people['stranger']
    dummy_contribution.update_principal(speaker, permissions={'submit'})
    assert _available('attach_link', speaker, event=dummy_event) is None
    assert _available('attach_link', speaker) is None  # without an event page too
    assert action_allows(ACTIONS['attach_link'], speaker, target_type='contribution', target_id=dummy_contribution.id,
                         url='https://example.org/slides')
    assert _available('add_reminder', speaker, event=dummy_event) is not None  # material only, not the meeting


@pytest.mark.parametrize('name', ['update_event', 'add_contribution', 'update_contribution', 'add_reminder',
                                  'attach_link'])
def test_without_an_event_page_it_follows_the_meetings_the_chat_can_find(people, dummy_event, name):
    assert _available(name, people['manager']) is None  # dummy_event starts now: the chat finds it by name
    assert _available(name, people['stranger']) == 'You do not manage any meeting'


@pytest.mark.parametrize('name', ['create_event', 'propose_event'])
@pytest.mark.parametrize('setup', ['nothing', 'create_permission', 'propose_permission', 'admin'])
def test_categories_a_reason_means_no_category_allows_it(action_allows, create_category, create_user, name, setup):
    category = create_category(title='Meetings', event_creation_mode=EventCreationMode.restricted)
    moderated = create_category(title='Moderated', event_creation_mode=EventCreationMode.moderated)
    user = create_user(30, admin=setup == 'admin')
    if setup == 'create_permission':
        category.update_principal(user, permissions={'create'})
    elif setup == 'propose_permission':
        moderated.update_principal(user, permissions={'event_move_request'})
    reason = _available(name, user)
    for each in Category.query.filter_by(is_deleted=False):
        in_it = _available(name, user, category=each)
        allowed = action_allows(ACTIONS[name], user, category_id=each.id, title='Sync', start_dt=LATER,
                                end_dt=LATER + timedelta(hours=1), timezone='UTC')
        assert (in_it is None) == allowed, (each.title, in_it)
        if reason is not None:
            assert not allowed, (each.title, reason)


def test_undo_is_always_offered(people):
    assert _available('delete_created', people['stranger']) is None  # it undoes only what it did in the chat


@pytest.mark.parametrize('name', ['update_event', 'add_contribution', 'add_reminder', 'attach_link'])
def test_without_an_event_page_a_locked_meeting_does_not_count(people, dummy_event, name):
    """(Copilot, PR #15) the checks refuse every change to a locked meeting"""
    dummy_event.is_locked = True
    assert _available(name, people['manager']) == 'The meetings you manage are locked'
