"""find_events returns exactly the events each user can open (spec 025 story 4, T068, SC-007)."""

from datetime import timedelta

from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.lookups import events


def titles(user, **filters):
    with acting_as(user):
        return [e.title for e in events.find_events(user, **filters)]


def test_each_kind_of_grant_opens_exactly_its_events(world):
    everything = {"text": "", "since": world.t0.date(), "until": (world.t0 + timedelta(days=10)).date()}
    assert titles(world.nora, **everything) == ["Team Sync", "Nora's Draft"]  # (public, and their own unlisted one)
    assert titles(world.dana, **everything) == ["Team Sync", "Briefing: Supplier Contracts"]  # a direct grant
    assert titles(world.lou, **everything) == ["Team Sync", "Lab Members Meeting"]  # a local group
    assert titles(world.ida, **everything) == ["Team Sync", "Physicists Forum"]  # an identity provider's group
    assert titles(world.cat, **everything) == ["Team Sync", "Restricted Roadmap Review"]  # the category's grant
    assert titles(world.manager, **everything) == [  # the category's manager opens its protected events
        "Team Sync",
        "Briefing: Supplier Contracts",
        "Lab Members Meeting",
        "Physicists Forum",
    ]


def test_a_protected_event_with_no_grant_is_not_found_by_name_or_id(world):
    assert titles(world.nora, text="Supplier Contracts") == []
    with acting_as(world.nora):
        assert events.get_event(world.nora, world.briefing.id) is None
    with acting_as(world.dana):
        assert events.get_event(world.dana, world.briefing.id) is world.briefing


def test_filters_by_date_category_and_text(world):
    day = (world.t0 + timedelta(days=1)).date()
    assert titles(world.nora, since=day, until=day) == ["Team Sync"]
    assert titles(world.nora, since=day + timedelta(days=1), until=day + timedelta(days=1)) == []
    assert titles(world.manager, category="team meetings", since=day) == [
        "Team Sync",
        "Briefing: Supplier Contracts",
        "Lab Members Meeting",
        "Physicists Forum",
    ]
    assert titles(world.nora, category="Restricted") == []
    assert titles(world.cat, category="Restricted") == ["Restricted Roadmap Review"]
    assert titles(world.nora, text="sync") == ["Team Sync"]


def test_an_unlisted_event_is_its_creators_only(world):
    assert titles(world.nora, text="Draft") == ["Nora's Draft"]
    assert titles(world.dana, text="Draft") == []
