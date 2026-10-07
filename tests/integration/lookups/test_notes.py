"""Notes only for objects the user can open (spec 025 story 4, T071)."""

from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.lookups import notes

from .conftest import note, talk


def test_notes_of_an_event_and_its_talks_follow_access(world):
    note(world.sync, "Decided: the cleanroom reopens Monday.", world.manager)
    note(world.briefing, "Contract SC-2291 approved.", world.manager)
    with acting_as(world.nora):
        assert [n["text"] for n in notes.notes_of(world.nora, world.sync)] == ["Decided: the cleanroom reopens Monday."]
        assert notes.search_notes(world.nora, "SC-2291") == []
        assert [n["event_title"] for n in notes.search_notes(world.nora, "cleanroom")] == ["Team Sync"]
    with acting_as(world.dana):
        found = notes.search_notes(world.dana, "SC-2291")
        assert [n["event_title"] for n in found] == ["Briefing: Supplier Contracts"] and "approved" in found[0]["text"]


def test_a_talks_notes_come_with_the_events(world):
    c = talk(world.sync, "Capacity planning", ("Priya", "Shah", "priya@example.test"))
    note(c, "Need two more racks.", world.manager)
    with acting_as(world.nora):
        found = notes.notes_of(world.nora, world.sync)
    assert [(n["about"], n["text"]) for n in found] == [("contribution “Capacity planning”", "Need two more racks.")]
