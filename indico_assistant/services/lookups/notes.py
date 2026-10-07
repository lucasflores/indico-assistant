"""Minutes and notes written in Indico, for objects the user can open (research R7: the view's own check)."""

from __future__ import annotations

from typing import Any

from indico.modules.events import Event
from indico.modules.events.notes.models.notes import EventNote
from indico.util.string import html_to_plaintext

SEARCH_LIMIT = 50
NOTE_CHARS = 4_000


def _text(note: EventNote) -> str:
    html = note.current_revision.html if note.current_revision else ""
    text = html_to_plaintext(html) if html and html.strip() else ""
    return text if len(text) <= NOTE_CHARS else text[:NOTE_CHARS].rstrip() + "…"


def _readable(note: EventNote, user: Any) -> bool:
    obj = note.object
    return (
        not note.is_deleted
        and obj is not None
        and not getattr(obj, "is_deleted", False)
        and not note.event.is_deleted
        and obj.can_access(user)
    )


def _about(note: EventNote) -> str:
    obj = note.object
    return "the event" if isinstance(obj, Event) else f"{type(obj).__name__.lower()} “{obj.title}”"


def notes_of(user: Any, event: Event) -> list[dict[str, Any]]:
    """The event's notes and those of its sessions, talks and subcontributions the user can open."""
    found = []
    for note in sorted(event.all_notes, key=lambda n: n.id):
        if _readable(note, user):
            found.append({"note": note.id, "event": event.id, "about": _about(note), "text": _text(note)})
    return found


def search_notes(user: Any, text: str) -> list[dict[str, Any]]:
    """Notes anywhere whose text matches ``text``, those the user can open, newest events first."""
    query = EventNote.query.filter(~EventNote.is_deleted, EventNote.html_matches(text)).limit(SEARCH_LIMIT)
    found = [n for n in query if _readable(n, user)]
    found.sort(key=lambda n: n.event.start_dt, reverse=True)
    return [
        {"note": n.id, "event": n.event.id, "event_title": n.event.title, "about": _about(n), "text": _text(n)}
        for n in found
    ]
