"""Permission parity (FR-003, SC-003): each US1 action refuses exactly when the Indico page doing the same
thing by hand refuses, for an admin, a manager, a contributions manager, a submitter and a stranger."""

import pytest

from indico.modules.categories.models.categories import EventCreationMode
from indico.modules.events.reminders.controllers import RHAddReminder
from indico.modules.events.timetable.controllers.legacy import RHLegacyTimetableAddContribution
from indico.modules.vc.controllers import RHVCManageEventCreate
from indico.util.date_time import now_utc

from indico_assistant.services.actions import ACTIONS


ROLES = ['admin', 'manager', 'contributions_manager', 'submitter', 'stranger']
LATER = now_utc() + __import__('datetime').timedelta(days=2)


@pytest.mark.parametrize('role', ROLES)
@pytest.mark.parametrize('locked', [False, True])
def test_add_contribution(page_allows, action_allows, people, dummy_event, role, locked):
    dummy_event.is_locked = locked
    user = people[role]
    page = page_allows(RHLegacyTimetableAddContribution, user, event=dummy_event, session=None)
    ours = action_allows(ACTIONS['add_contribution'], user, event_id=dummy_event.id, title='Talk', start_dt=LATER,
                         duration_minutes=20)
    assert ours == page, role


@pytest.mark.parametrize('role', ROLES)
@pytest.mark.parametrize('locked', [False, True])
def test_add_reminder(page_allows, action_allows, people, dummy_event, role, locked):
    dummy_event.is_locked = locked
    user = people[role]
    assert action_allows(ACTIONS['add_reminder'], user, event_id=dummy_event.id, minutes_before=15) == \
        page_allows(RHAddReminder, user, event=dummy_event), role


@pytest.mark.parametrize('role', ROLES)
@pytest.mark.parametrize('acl', ['everyone', 'only_admins'])
def test_add_teams_room(page_allows, action_allows, people, dummy_event, teams, role, acl):
    plugin, _ = teams
    if acl == 'only_admins':
        plugin.settings.acls.set('acl', {people['admin']})  # the plugin's "who may create rooms" setting
    user = people[role]
    page = page_allows(RHVCManageEventCreate, user, lambda: plugin.can_manage_vc_rooms(user, dummy_event),
                       event=dummy_event)
    ours = action_allows(ACTIONS['add_teams_room'], user, event_id=dummy_event.id, name='Sync', coorganizer_ids=[])
    assert ours == page, role


def test_add_teams_room_without_the_plugin(action_allows, people, dummy_event, monkeypatch):
    from indico_assistant.services.actions import teams as teams_action
    monkeypatch.setattr(teams_action, 'teams_plugin', lambda: None)
    assert not action_allows(ACTIONS['add_teams_room'], people['admin'], event_id=dummy_event.id, name='Sync')


def test_add_teams_room_refuses_people_without_a_tenant_account(action_allows, people, dummy_event, teams):
    _, fake = teams
    fake.add_missing_user('makoto@aithoth.com')
    assert not action_allows(ACTIONS['add_teams_room'], people['manager'], event_id=dummy_event.id, name='Sync',
                             coorganizer_ids=[people['makoto'].id])


@pytest.mark.parametrize(('setup', 'expected'), [
    ('admin', True), ('category_manager', True), ('create_permission', True), ('open_mode', True),
    ('restricted', False),
])
def test_create_event(action_allows, create_category, create_user, setup, expected):
    # the creation form's rule for a listed event (EventCreationFormBase.validate_category)
    category = create_category(title='Meetings', event_creation_mode=EventCreationMode.restricted)
    user = create_user(20, admin=setup == 'admin')
    if setup == 'category_manager':
        category.update_principal(user, full_access=True)
    elif setup == 'create_permission':
        category.update_principal(user, permissions={'create'})
    elif setup == 'open_mode':
        category.event_creation_mode = EventCreationMode.open
    assert category.can_create_events(user) is expected
    assert action_allows(ACTIONS['create_event'], user, category_id=category.id, title='Sync', start_dt=LATER,
                         end_dt=LATER + __import__('datetime').timedelta(minutes=30), timezone='UTC') is expected
