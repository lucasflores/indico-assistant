"""The lookups as the turn's tools (spec 025 story 4, T073): what they return, and what they remember."""

import json
from datetime import timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from indico_assistant.services.turn import lookups
from indico_assistant.services.turn.tools import Ctx

from .conftest import note, talk


def make_ctx(user):
    return Ctx(
        user=user,
        session_id=uuid4(),
        message_id=None,
        page_event_id=None,
        history=[],
        settings={},
        llm=MagicMock(),
        base_url="https://indico.test",
    )


def by_name(name):
    return next(t for t in lookups.LOOKUP_TOOLS if t.name == name)


def run(name, ctx, **args):
    tool = by_name(name)
    return tool.run(ctx, tool.args(tool=name, **args))


def test_find_events_lists_what_the_user_may_open_and_remembers_them(world):
    ctx = make_ctx(world.nora)
    text = run("find_events", ctx, since=world.t0.date(), until=(world.t0 + timedelta(days=10)).date())
    records = [json.loads(line) for line in text.splitlines()]
    assert [r["title"] for r in records] == ["Team Sync", "Nora's Draft"] and "Supplier" not in text
    assert records[0]["event"] == world.sync.id and "url" in records[0] and "when" in records[0]
    assert [(e["kind"], e["position"]) for e in ctx.memory.touched] == [("event", 1), ("event", 2)]
    assert run("find_events", make_ctx(world.nora)) == "Give at least one of: text, since/until, category, person."
    assert run("find_events", make_ctx(world.nora), text="Supplier") == "No events found that the user can open."


def test_get_event_hides_a_protected_events_existence(world):
    assert run("get_event", make_ctx(world.nora), event=world.briefing.id) == lookups.NOT_FOUND.format(
        id=world.briefing.id
    )
    ctx = make_ctx(world.dana)
    found = json.loads(run("get_event", ctx, event=world.briefing.id))
    assert found["title"] == "Briefing: Supplier Contracts" and "managers" not in found  # (not a manager)
    assert json.loads(run("get_event", make_ctx(world.manager), event=world.briefing.id))["managers"]


def test_a_persons_talks_are_listed_and_remembered(world):
    c = talk(world.sync, "Capacity planning", ("Priya", "Shah", "priya@example.test"))
    ctx = make_ctx(world.nora)
    [record] = [json.loads(line) for line in run("find_events", ctx, person="Priya Shah").splitlines()]
    assert record["talks"] == [f"Capacity planning (contribution {c.id})"]
    assert {
        "kind": "contribution",
        "ref": {"contribution_id": c.id},
        "title": "Capacity planning",
        "position": 1,
    } in ctx.memory.touched


def test_get_timetable_and_registrations_name_the_event(world):
    talk(world.sync, "Capacity planning", ("Priya", "Shah", "priya@example.test"))
    ctx = make_ctx(world.nora)
    text = run("get_timetable", ctx, event=world.sync.id)
    assert text.startswith(f"Team Sync (event {world.sync.id})") and "Capacity planning" in text
    assert [e["kind"] for e in ctx.memory.touched] == ["event", "contribution"]
    text = run("get_registrations", make_ctx(world.nora), event=world.sync.id)
    assert text.startswith(f"Team Sync (event {world.sync.id})") and '"published": false' in text


def test_get_notes_by_event_and_by_words(world):
    note(world.sync, "Decided: the cleanroom reopens Monday.", world.manager)
    note(world.briefing, "Contract SC-2291 approved.", world.manager)
    ctx = make_ctx(world.nora)
    assert "cleanroom" in run("get_notes", ctx, event=world.sync.id)
    assert run("get_notes", make_ctx(world.nora), text="SC-2291") == "No notes mention that (that the user can open)."
    found = run("get_notes", ctx, text="cleanroom")
    assert '"event_title": "Team Sync"' in found and [e["kind"] for e in ctx.memory.touched] == ["event", "note"]
    assert run("get_notes", make_ctx(world.nora)) == "Give an event, or words the notes mention."
