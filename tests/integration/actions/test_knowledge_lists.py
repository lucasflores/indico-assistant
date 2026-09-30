"""The two lists a knowledge answer gets, built for one user (spec 022, FR-008 to FR-011): what the assistant can do
for them, and the pages they can open."""

import pytest
from indico.core.config import config
from indico.modules.categories.models.categories import EventCreationMode

from indico_assistant.default_settings import DEFAULT_SETTINGS, WRITE_ACTIONS
from indico_assistant.services.actions import ACTIONS
from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.actions.resolve import creatable_categories
from indico_assistant.services.knowledge.capabilities import NEVER, capability_list
from indico_assistant.services.knowledge.pages import page_list

SETTINGS = {**DEFAULT_SETTINGS, "actions_enabled": True, "actions_allowed": list(WRITE_ACTIONS)}


def _caps(user, event=None, settings=SETTINGS):
    with acting_as(user):
        return capability_list(user, event, settings)


def _pages(user, event=None):
    with acting_as(user):
        return page_list(user, event)


def test_a_manager_on_their_event(people, dummy_event, teams):
    caps = _caps(people["manager"], dummy_event)
    assert caps.event["manages"] is True
    assert ACTIONS["add_contribution"].summary in caps.can and ACTIONS["add_teams_room"].summary in caps.can
    text = caps.render()
    assert dummy_event.title in text and "They manage it" in text
    assert all(item in text for item in NEVER)


def test_someone_who_cannot_manage_the_event(people, dummy_event, teams):
    caps = _caps(people["stranger"], dummy_event)
    assert caps.event["manages"] is False
    reasons = dict(caps.cannot)
    assert f"You cannot manage the event “{dummy_event.title}”" == reasons[ACTIONS["update_event"].summary]
    assert ACTIONS["add_teams_room"].summary in reasons
    assert "They do NOT manage it" in caps.render()


def test_the_categories_are_the_ones_indico_allows(people, create_category):
    category = create_category(title="Team Meetings", event_creation_mode=EventCreationMode.restricted)
    user = people["stranger"]
    before = _caps(user)
    category.update_principal(user, permissions={"create"})
    after = _caps(user)  # nothing is cached between questions (spec US2 AS-5)
    assert "Team Meetings" not in before.create_in and "Team Meetings" in after.create_in
    with acting_as(user):
        assert after.create_in == [c.title for c in creatable_categories(user)]
    if not before.create_in:
        assert ACTIONS["create_event"].summary in dict(before.cannot)


def test_an_action_the_admin_switched_off(people, dummy_event):
    settings = {**SETTINGS, "actions_allowed": [a for a in WRITE_ACTIONS if a != "add_reminder"]}
    caps = _caps(people["manager"], dummy_event, settings)
    assert dict(caps.cannot)[ACTIONS["add_reminder"].summary] == "switched off by the administrator"
    off = _caps(people["manager"], dummy_event, {**SETTINGS, "actions_enabled": False})
    assert not off.can and "It cannot change anything in Indico here" in off.render()


def test_without_an_event_page(people, dummy_event):
    caps = _caps(people["manager"])
    assert caps.event is None and ACTIONS["update_event"].summary in caps.can  # the chat finds the meeting by name
    assert "You do not manage any meeting" in dict(_caps(people["stranger"]).cannot).values()


def test_data_questions_follow_the_settings(people):
    assert "It cannot answer questions about event data" in _caps(people["manager"], settings={
        **SETTINGS, "nl2sql_enabled": False}).render()


def test_the_page_lists_of_a_manager_and_a_stranger(people, dummy_event):
    managed = {p.path for p in _pages(people["manager"], dummy_event)}
    stranger = {p.path for p in _pages(people["stranger"], dummy_event)}
    assert f"/event/{dummy_event.id}/manage/" in managed and f"/event/{dummy_event.id}/manage/protection" in managed
    assert not any("/manage" in p for p in stranger)
    assert f"/event/{dummy_event.id}/" in stranger and "/user/tokens/" in stranger & managed
    rooms = [p for p in _pages(people["stranger"]) if p.title == "Room booking"]
    assert bool(rooms) == bool(config.ENABLE_ROOMBOOKING)


def test_the_page_list_is_built_as_the_user_only(people, dummy_event):
    with acting_as(people["manager"]), pytest.raises(RuntimeError):
        page_list(people["stranger"], dummy_event)  # never another user's menus
