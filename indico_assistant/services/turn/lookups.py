"""The typed lookups as the turn's tools (spec 025 story 4, contracts/agent-tools.md): events, one event, a
programme, registrations, notes. Each runs as the user (``acting_as``) and returns what Indico lets them open."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from indico_assistant.services.connectors import Tool
from indico_assistant.services.lookups import events as events_lookup
from indico_assistant.services.lookups import notes as notes_lookup
from indico_assistant.services.lookups import registrations as registrations_lookup
from indico_assistant.services.lookups import timetable as timetable_lookup
from indico_assistant.services.turn.tools import Ctx

NOT_FOUND = "No event {id} that the user can open."


class FindEventsArgs(BaseModel):
    """Events and meetings the user can open, by any of: words in the title or description; a date range (ISO dates,
    in the user's time zone: a day is since=until=that day, "next week" is its Monday to Sunday, counted from
    today's date in the prompt); a category's name; a person's name (who speaks, presents or chairs). Up to 20,
    soonest first, with id, dates, place and category: then get_event, get_timetable, get_registrations or get_notes
    by id for more."""

    tool: Literal["find_events"]
    text: str | None = Field(None, description="Words of the title or description")
    since: date | None = Field(None, description="First day (YYYY-MM-DD)")
    until: date | None = Field(None, description="Last day (YYYY-MM-DD)")
    category: str | None = Field(None, description="A category's name, or part of it")
    person: str | None = Field(None, description="A person's name: events where they speak or chair")


class GetEventArgs(BaseModel):
    """One event in full: dates, place, description, chairpersons, contact and link."""

    tool: Literal["get_event"]
    event: int


class GetTimetableArgs(BaseModel):
    """An event's programme: its talks (contributions) with times, speakers and rooms, its sessions and breaks, as
    the user may see them."""

    tool: Literal["get_timetable"]
    event: int


class GetRegistrationsArgs(BaseModel):
    """Who registered for an event: the management list for its registration managers, otherwise the published
    participant list (as Indico shows it: the form's setting, each registrant's consent, the columns shown)."""

    tool: Literal["get_registrations"]
    event: int


class GetNotesArgs(BaseModel):
    """Minutes and notes written in Indico: an event's (with its talks' notes), or, without an event, the notes
    anywhere that mention some words."""

    tool: Literal["get_notes"]
    event: int | None = None
    text: str | None = Field(None, description="Words the notes mention (when no event is given)")


def _lines(records: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in records)


def _find_events(ctx: Ctx, args: FindEventsArgs) -> str:
    from indico_assistant.services.actions.context import acting_as

    if not any((args.text, args.since, args.until, args.category, args.person)):
        return "Give at least one of: text, since/until, category, person."
    with acting_as(ctx.user):
        events = events_lookup.find_events(
            ctx.user, text=args.text, since=args.since, until=args.until, category=args.category, person=args.person
        )
        talks = events_lookup.talks_by(ctx.user, args.person, events) if args.person else {}
        records = []
        for e in events:
            record = events_lookup.describe(e, ctx.user)
            if args.person:
                record["talks"] = [f"{c.title} (contribution {c.id})" for c in talks.get(e.id, [])] or None
                for c in talks.get(e.id, []):
                    ctx.memory.add("contribution", {"contribution_id": c.id}, c.title)
            ctx.memory.add("event", {"event_id": e.id}, e.title)
            records.append({k: v for k, v in record.items() if v is not None})
    if not records:
        return "No events found that the user can open."
    more = (
        f"\n(the first {events_lookup.LIMIT}: narrow the search for others)"
        if len(records) >= events_lookup.LIMIT
        else ""
    )
    return _lines(records) + more


def _get_event(ctx: Ctx, args: GetEventArgs) -> str:
    from indico_assistant.services.actions.context import acting_as

    with acting_as(ctx.user):
        event = events_lookup.get_event(ctx.user, args.event)
        if event is None:
            return NOT_FOUND.format(id=args.event)
        ctx.memory.add("event", {"event_id": event.id}, event.title)
        return json.dumps(events_lookup.describe(event, ctx.user, full=True), ensure_ascii=False)


def _get_timetable(ctx: Ctx, args: GetTimetableArgs) -> str:
    from indico_assistant.services.actions.context import acting_as

    with acting_as(ctx.user):
        event = events_lookup.get_event(ctx.user, args.event)
        if event is None:
            return NOT_FOUND.format(id=args.event)
        ctx.memory.add("event", {"event_id": event.id}, event.title)
        lines = timetable_lookup.timetable(ctx.user, event)
        for entry in timetable_lookup.remembered(ctx.user, event):
            ctx.memory.add("contribution", {"contribution_id": entry["id"]}, entry["title"])
    return f"{event.title} (event {event.id}), {events_lookup.when(event)}:\n" + "\n".join(lines)


def _get_registrations(ctx: Ctx, args: GetRegistrationsArgs) -> str:
    from indico_assistant.services.actions.context import acting_as

    with acting_as(ctx.user):
        event = events_lookup.get_event(ctx.user, args.event)
        if event is None:
            return NOT_FOUND.format(id=args.event)
        ctx.memory.add("event", {"event_id": event.id}, event.title)
        found = registrations_lookup.registrations(ctx.user, event)
    return f"{event.title} (event {event.id}):\n" + json.dumps(found, ensure_ascii=False)


def _get_notes(ctx: Ctx, args: GetNotesArgs) -> str:
    from indico_assistant.services.actions.context import acting_as

    with acting_as(ctx.user):
        if args.event is not None:
            event = events_lookup.get_event(ctx.user, args.event)
            if event is None:
                return NOT_FOUND.format(id=args.event)
            ctx.memory.add("event", {"event_id": event.id}, event.title)
            found = notes_lookup.notes_of(ctx.user, event)
            if not found:
                return f"{event.title} has no notes the user can open."
        elif args.text:
            found = notes_lookup.search_notes(ctx.user, args.text)
            if not found:
                return "No notes mention that (that the user can open)."
            for n in found:
                ctx.memory.add("event", {"event_id": n["event"]}, n["event_title"])
        else:
            return "Give an event, or words the notes mention."
    for n in found:
        ctx.memory.add("note", {"note_id": n["note"]}, f"notes of {n.get('event_title') or 'event ' + str(n['event'])}")
    return _lines(found)


LOOKUP_TOOLS = (
    Tool("find_events", FindEventsArgs, _find_events),
    Tool("get_event", GetEventArgs, _get_event),
    Tool("get_timetable", GetTimetableArgs, _get_timetable),
    Tool("get_registrations", GetRegistrationsArgs, _get_registrations),
    Tool("get_notes", GetNotesArgs, _get_notes),
)
