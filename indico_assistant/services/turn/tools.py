"""The turn's tools: what each is, what it is given, and the document tools (spec 025, contracts/agent-tools.md).

A tool is the connectors' ``Tool`` (``services/connectors``): a name, an args model with a literal ``tool`` field
whose docstring the model reads, and ``run(ctx, args) -> str``. ``ctx`` carries the acting user, the chat, the page,
the memory and what the turn gathers (links it may keep, a plan, privacy). Every tool:
- runs as the user and checks access itself (the document tools through Indico's ``can_access``);
- returns short text, cut to a fixed size; the loop marks it as untrusted data;
- records the things it presented in the memory, so later turns can refer to them;
- returns an error as text, and raises only the worker's time limit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from indico_assistant.services.connectors import Tool
from indico_assistant.services.turn.memory import Memory

__all__ = ["Ctx", "Tool", "DOCUMENT_TOOLS"]


@dataclass
class Ctx:
    """What a tool gets: who asks, where, and what the turn has gathered so far."""

    user: Any
    session_id: UUID
    message_id: UUID | None
    page_event_id: int | None
    history: list[dict[str, str]]
    settings: dict[str, Any]
    llm: Any
    base_url: str
    memory: Memory = field(default_factory=Memory)
    embedder: Any = None
    allowed_tables: list[str] | None = None
    waiting_plan: Any = None
    offer: str | None = None
    started: float | None = None
    # gathered by the tools
    plan: tuple[str, dict[str, Any], dict[str, Any] | None] | None = None  # the planner's (reply, metadata, plan)
    knowledge_offer: str | None = None  # a change the guide's answer offered to make
    link_paths: set[str] = field(default_factory=set)  # this Indico's pages a tool linked (the answer may keep them)
    guide_urls: set[str] = field(default_factory=set)
    github_urls: set[str] = field(default_factory=set)
    private: bool = False  # GitHub was read: no text is kept (spec 024)
    pages_seen: dict[int, set[int]] = field(default_factory=dict)  # document -> pages a tool returned (citations)
    page_documents: list[dict[str, Any]] = field(default_factory=list)  # the page's documents, in the prompt (FR-011)

    def saw(self, document: int, pages: Any) -> None:
        self.pages_seen.setdefault(document, set()).update(pages)

    data: dict[str, Any] = field(default_factory=dict)  # the data tool's metadata (SQL, sources), for the answer


def _events(ids: Any) -> dict[int, str]:
    """Event titles by id, for naming where a document is attached."""
    from indico.modules.events import Event

    ids = {i for i in ids if i is not None}
    return {e.id: e.title for e in Event.query.filter(Event.id.in_(ids))} if ids else {}


def _embedder(ctx: Ctx) -> Any:
    if ctx.embedder is None:
        from indico_assistant.plugin import AssistantPlugin
        from indico_assistant.services.embedding import EmbeddingService

        ctx.embedder = EmbeddingService(AssistantPlugin.instance)
    return ctx.embedder


# --- documents ---------------------------------------------------------------------------------------------------


class ListDocumentsArgs(BaseModel):
    """The documents in a scope: the user's current page ("page"), the ones this conversation has touched
    ("conversation"), or an event's ("event:<id>"). Each comes with its id, file name, status, pages and top-level
    sections."""

    tool: Literal["list_documents"]
    scope: str = Field("page", pattern=r"^(page|conversation|event:\d+)$")


class ReadDocumentArgs(BaseModel):
    """Read one document by id: its start (title, abstract, introduction) by default, up to 5 pages, or one section
    by number ("4.4.1") or title. Each page comes labelled [p.N]: cite those numbers."""

    tool: Literal["read_document"]
    document: int
    pages: list[int] | None = Field(None, description="Page (or slide) numbers, at most 5")
    section: str | None = Field(None, description="A section number or title")


class SearchDocumentsArgs(BaseModel):
    """Find passages in documents. Write the query yourself: the key terms or a short phrase, not the user's whole
    message; put an exact term in quotes. Searches one document, an event's, or (neither) every document the user
    can open. Returns the 8 best passages with their document, page and section."""

    tool: Literal["search_documents"]
    query: str
    document: int | None = None
    event: int | None = None


def _list_documents(ctx: Ctx, args: ListDocumentsArgs) -> str:
    from indico_assistant.services.document import reader

    if args.scope == "page":
        if ctx.page_event_id is None:
            return "The user is not on an event page now."
        docs = reader.documents(ctx.user, event_id=ctx.page_event_id)
    elif args.scope == "conversation":
        docs = reader.documents(ctx.user, attachment_ids=ctx.memory.documents())
    else:
        docs = reader.documents(ctx.user, event_id=int(args.scope.split(":")[1]))
    if not docs:
        return "No documents there that the user can open."
    titles = _events(d.event_id for d in docs)
    for d in docs:
        ctx.memory.add("document", {"attachment_id": d.attachment_id}, d.filename)
    return "\n".join(
        json.dumps({**reader.describe(d), "event": f"{d.event_id}: {titles.get(d.event_id, '')}"}, ensure_ascii=False)
        for d in docs
    )


def _read_document(ctx: Ctx, args: ReadDocumentArgs) -> str:
    from indico_assistant.models.document import Document
    from indico_assistant.services.document import reader

    text = reader.read(
        ctx.user, args.document, start=not (args.pages or args.section), pages=args.pages, section=args.section
    )
    doc = Document.query.get(args.document)
    if doc is not None and not text.startswith("No document"):
        ctx.memory.add("document", {"attachment_id": doc.attachment_id}, doc.filename)
        ctx.saw(doc.attachment_id, (int(n) for n in re.findall(r"^\[p\.(\d+)\]$", text, re.M)))
        title = _events([doc.event_id]).get(doc.event_id, "")
        text = f"(attached to event {doc.event_id}: {title})\n{text}"
    return text


def _search_documents(ctx: Ctx, args: SearchDocumentsArgs) -> str:
    from indico_assistant.services.document.search import search

    hits = search(ctx.user, args.query, attachment_id=args.document, event_id=args.event, embedder=_embedder(ctx))
    if not hits:
        return "No passages found."
    out = []
    titles = _events(h.event_id for h in hits)
    for h in hits:
        ctx.memory.add("document", {"attachment_id": h.attachment_id}, h.filename)
        ctx.saw(h.attachment_id, [h.page])
        event = f", in event {h.event_id}: {titles.get(h.event_id, '')}" if h.event_id is not None else ""
        where = f"document {h.attachment_id} ({h.filename}{event}), [p.{h.page}]" + (
            f", {h.section}" if h.section else ""
        )
        out.append(f"{where}:\n{h.text}")
    return "\n\n".join(out)


DOCUMENT_TOOLS = (
    Tool("list_documents", ListDocumentsArgs, _list_documents),
    Tool("read_document", ReadDocumentArgs, _read_document),
    Tool("search_documents", SearchDocumentsArgs, _search_documents),
)
