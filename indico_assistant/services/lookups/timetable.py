"""An event's programme as Indico shows it to the user (research R7): ``TimetableSerializer`` with ``user``, which
drops every entry ``can_view`` refuses; while the programme is unpublished, non-managers get none of it (api.py)."""

from __future__ import annotations

from typing import Any

from indico.modules.events import Event
from indico.modules.events.contributions import contribution_settings
from indico.modules.events.timetable.legacy import TimetableSerializer

UNPUBLISHED = "The programme of this event is not published yet."


def _people(entry: dict[str, Any]) -> str:
    people = entry.get("presenters") or entry.get("conveners") or []
    names = [p["name"] + (f" ({p['affiliation']})" if p.get("affiliation") else "") for p in people]
    return ", ".join(names)


def _line(entry: dict[str, Any], indent: str = "") -> str:
    start, end = entry.get("startDate") or {}, entry.get("endDate") or {}
    hours = f"{start.get('time', '')[:5]}–{end.get('time', '')[:5]}"
    kind = entry.get("entryType")
    title = entry.get("title") or entry.get("slotTitle") or ""
    ref = f" (contribution {entry['contributionId']})" if kind == "Contribution" and entry.get("contributionId") else ""
    who = _people(entry)
    room = entry.get("room")
    return f"{indent}- {hours} {kind}: {title}{ref}" + (f" — {who}" if who else "") + (f" [{room}]" if room else "")


def timetable(user: Any, event: Event) -> list[str]:
    """One line per entry, by day, as the user may see it; ``[UNPUBLISHED]`` when they may not yet."""
    if not contribution_settings.get(event, "published") and not event.can_manage(user):
        return [UNPUBLISHED]
    days = TimetableSerializer(event, management=False, user=user, api=True).serialize_timetable()
    lines: list[str] = []
    for day, entries in sorted(days.items()):
        ordered = sorted(entries.values(), key=lambda e: (e.get("startDate") or {}).get("time", ""))
        if not ordered:
            continue
        lines.append(f"{day[:4]}-{day[4:6]}-{day[6:]} ({(ordered[0].get('startDate') or {}).get('tz', '')}):")
        for entry in ordered:
            lines.append(_line(entry))
            for child in sorted(
                (entry.get("entries") or {}).values(), key=lambda e: (e.get("startDate") or {}).get("time", "")
            ):
                lines.append(_line(child, "  "))
    return lines or ["(the timetable is empty)"]


def remembered(user: Any, event: Event) -> list[dict[str, Any]]:
    """The contributions the user may see in the programme, as (id, title), for the memory."""
    if not contribution_settings.get(event, "published") and not event.can_manage(user):
        return []
    days = TimetableSerializer(event, management=False, user=user, api=True).serialize_timetable()
    found = []
    for entries in days.values():
        for entry in entries.values():
            children = [entry, *(entry.get("entries") or {}).values()]
            found += [
                {"id": c["contributionId"], "title": c.get("title") or ""}
                for c in children
                if c.get("entryType") == "Contribution" and c.get("contributionId")
            ]
    return found
