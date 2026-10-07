"""The programme as the user may see it (spec 025 story 4, T069): unpublished contributions for managers only."""

from indico.modules.events.contributions import contribution_settings

from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.lookups import events, timetable

from .conftest import talk


def test_speakers_and_times_and_the_published_switch(world):
    priya = ("Priya", "Shah", "priya@example.test")
    talk(world.sync, "Capacity planning", priya)
    with acting_as(world.nora):
        lines = timetable.timetable(world.nora, world.sync)
    assert any("Contribution: Capacity planning" in line and "Priya Shah" in line for line in lines)
    contribution_settings.set(world.sync, "published", False)
    with acting_as(world.nora):
        assert timetable.timetable(world.nora, world.sync) == [timetable.UNPUBLISHED]
        assert timetable.remembered(world.nora, world.sync) == []
    with acting_as(world.manager):
        assert any("Capacity planning" in line for line in timetable.timetable(world.manager, world.sync))


def test_a_persons_talks_follow_the_same_rules(world):
    from indico.core.db.sqlalchemy.protection import ProtectionMode

    priya = ("Priya", "Shah", "priya@example.test")
    talk(world.sync, "Capacity planning", priya)
    closed = talk(world.sync, "Closed walkthrough", priya)  # (a protected talk inside an open event)
    closed.protection_mode = ProtectionMode.protected
    closed.update_principal(world.dana, read_access=True)
    talk(world.briefing, "Supplier scoring", priya)
    with acting_as(world.nora):
        found = events.find_events(world.nora, person="Priya Shah")
        assert [e.title for e in found] == ["Team Sync"]
        assert [c.title for c in events.talks_by(world.nora, "Shah", found)[world.sync.id]] == ["Capacity planning"]
    with acting_as(world.dana):
        found = events.find_events(world.dana, person="Priya")
        assert [e.title for e in found] == ["Team Sync", "Briefing: Supplier Contracts"]
        assert [c.title for c in events.talks_by(world.dana, "Priya", found)[world.sync.id]] == [
            "Capacity planning",
            "Closed walkthrough",
        ]
