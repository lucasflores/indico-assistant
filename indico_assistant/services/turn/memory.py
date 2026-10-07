"""The conversation's memory: what earlier answers touched, by id (spec 025, data-model "Conversation memory").

Kinds: ``document`` (attachment_id), ``event`` (event_id, from the data tool's sources), ``plan`` (plan_id) and
``github`` (an item's or a repository's url; only a turn that read GitHub has them, and it is private).

Each answer stores the things it presented, in order, in its message's ``metadata_json["touched"]``:
``{kind, ref, title, position}``. The next turn reads them, so "the second one" or "that thesis" resolves to an id.
Nothing about access is stored: every use checks again, as the user (FR-021).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from indico_assistant.models.message import ChatMessage

EARLIER_ANSWERS = 5  # the last answers whose touched lists are remembered
MAX_ENTRIES = 30


@dataclass
class Memory:
    earlier: list[dict[str, Any]] = field(default_factory=list)  # the last answer's list first, then older ones
    touched: list[dict[str, Any]] = field(default_factory=list)  # this turn's, in the order they were presented

    def add(self, kind: str, ref: dict[str, Any], title: str) -> None:
        """Remember something this turn presented; its position counts within its kind ("the second document")."""
        if any(e["kind"] == kind and e["ref"] == ref for e in self.touched):
            return
        position = sum(e["kind"] == kind for e in self.touched) + 1
        self.touched.append({"kind": kind, "ref": ref, "title": title, "position": position})

    def documents(self) -> list[int]:
        """The documents this conversation has touched, newest first."""
        ids = [e["ref"]["attachment_id"] for e in [*self.touched, *self.earlier] if e["kind"] == "document"]
        return list(dict.fromkeys(ids))

    def render(self) -> str:
        """For the prompt: what earlier answers presented, with their ids and positions."""
        if not self.earlier:
            return "(nothing yet)"
        lines = []
        for e in self.earlier:
            ref = ", ".join(f"{k} {v}" for k, v in e["ref"].items())
            lines.append(f"- {e['kind']} #{e['position']}: {e['title']} ({ref})")
        return "\n".join(lines)


def load(session_id: UUID, up_to: UUID | None, answers: int = EARLIER_ANSWERS) -> list[dict[str, Any]]:
    """The touched lists of the last ``answers`` answers before ``up_to``: the most recent answer's first (so "the
    second one" is its second), each thing once."""
    query = ChatMessage.query.filter(ChatMessage.session_id == session_id, ChatMessage.role == "assistant")
    if up_to is not None:
        query = query.filter(
            ChatMessage.created_at
            < ChatMessage.query.with_entities(ChatMessage.created_at).filter_by(id=up_to).scalar_subquery()
        )
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for message in query.order_by(ChatMessage.created_at.desc()).limit(answers):
        for e in (message.metadata_json or {}).get("touched") or []:
            key = (e.get("kind"), repr(sorted((e.get("ref") or {}).items())))
            if key not in seen and e.get("kind") and isinstance(e.get("ref"), dict):
                seen.add(key)
                entries.append(e)
    return entries[:MAX_ENTRIES]


def usable(user: Any, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The entries the user may still use: a document or an event they can no longer open is dropped (FR-021)."""
    from indico.modules.events import Event

    from indico_assistant.services.document.search import accessible

    documents = [e["ref"]["attachment_id"] for e in entries if e["kind"] == "document"]
    allowed = set(accessible(user, documents)) if documents else set()
    ids = [e["ref"]["event_id"] for e in entries if e["kind"] == "event"]
    events = Event.query.filter(Event.id.in_(ids), ~Event.is_deleted).all() if ids else []
    open_events = {e.id for e in events if e.can_access(user)}
    return [
        e
        for e in entries
        if (e["kind"] != "document" or e["ref"]["attachment_id"] in allowed)
        and (e["kind"] != "event" or e["ref"]["event_id"] in open_events)
    ]
