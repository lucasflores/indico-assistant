"""Reading documents for the agent: lists, starts, pages and sections (spec 025, contracts/agent-tools.md).

Every function takes the acting user and returns only documents whose attachment that user can open. Text comes
back with each page labelled ``[p.N]``, the label answers cite. A document that isn't ready says why instead.
"""

from __future__ import annotations

from typing import Any

from indico.core.db import db
from sqlalchemy import text

from indico_assistant.models.document import Document, DocumentStatus
from indico_assistant.services.document.chunker import join
from indico_assistant.services.document.search import accessible
from indico_assistant.services.document.structure import find, label

MAX_PAGES = 5  # per read
MAX_CHARS = 12000  # per read
START_CHARS = 6000  # "the start": title, abstract, introduction

NOT_READY = {
    DocumentStatus.QUEUED.value: "is still being read; try again in a minute",
    DocumentStatus.READING.value: "is still being read; try again in a minute",
    DocumentStatus.NO_TEXT.value: "has no text to read (it may be a scan)",
    DocumentStatus.FAILED.value: "could not be read",
    DocumentStatus.UNSUPPORTED.value: "is a file type (or size) the assistant can't read",
}


def documents(user: Any, *, event_id: int | None = None, attachment_ids: list[int] | None = None) -> list[Document]:
    """The documents of an event or with these ids that ``user`` can open, in upload order."""
    query = Document.query
    if event_id is not None:
        query = query.filter(Document.event_id == event_id)
    if attachment_ids is not None:
        query = query.filter(Document.attachment_id.in_(attachment_ids))
    docs = query.order_by(Document.attachment_id).all()
    allowed = set(accessible(user, [d.attachment_id for d in docs]))
    return [d for d in docs if d.attachment_id in allowed]


def describe(doc: Document) -> dict[str, Any]:
    """What the agent's document list shows: id, name, status, size, and the top of the outline."""
    entry: dict[str, Any] = {"document": doc.attachment_id, "filename": doc.filename, "status": doc.status}
    if doc.status != DocumentStatus.READY.value:
        entry["note"] = NOT_READY.get(doc.status, "")
    if doc.page_count:
        entry["pages"] = doc.page_count
    outline = [s for s in (doc.outline or []) if s.get("level") == 1]
    if outline:
        entry["outline"] = [f"{label(s)} (p.{s['page_start']})" for s in outline[:30]]
    return entry


PREVIEW_CHARS = 300


def describe_all(docs: list[Document]) -> list[dict[str, Any]]:
    """``describe`` for each, with how its first page begins (where the title usually is: filenames like
    1706.03762v7.pdf don't name a paper)."""
    ids = [d.attachment_id for d in docs if d.status == DocumentStatus.READY.value]
    begins: dict[int, str] = {}
    if ids:
        rows = db.session.execute(
            text("""
                SELECT DISTINCT ON (attachment_id) attachment_id, left(text, :n) FROM plugin_assistant.document_chunks
                WHERE attachment_id = ANY(:ids) ORDER BY attachment_id, chunk_index
                """),
            {"ids": ids, "n": PREVIEW_CHARS},
        )
        begins = {row[0]: " ".join(row[1].split()) for row in rows}
    return [{**describe(d), **({"begins": begins[d.attachment_id]} if d.attachment_id in begins else {})} for d in docs]


def pages_text(attachment_id: int, numbers: list[int]) -> dict[int, str]:
    """Those pages' text, rebuilt from their chunks."""
    rows = db.session.execute(
        text("""
        SELECT page, "offset", text FROM plugin_assistant.document_chunks
        WHERE attachment_id = :id AND page = ANY(:pages) ORDER BY page, chunk_index
    """),
        {"id": attachment_id, "pages": numbers},
    )
    pieces: dict[int, list[tuple[int, str]]] = {}
    for page, offset, chunk in rows:
        pieces.setdefault(page, []).append((offset, chunk))
    return {page: join(parts) for page, parts in pieces.items()}


def _labelled(attachment_id: int, numbers: list[int], budget: int = MAX_CHARS) -> str:
    out: list[str] = []
    used = 0
    texts = pages_text(attachment_id, numbers)
    for n in numbers:
        page = texts.get(n, "")
        if used + len(page) > budget and out:
            out.append(f"[stopped before p.{n}: ask for it to read on]")
            break
        out.append(f"[p.{n}]\n{page[: budget - used]}")
        used += len(page)
    return "\n\n".join(out)


def read(
    user: Any, attachment_id: int, *, start: bool = False, pages: list[int] | None = None, section: str | None = None
) -> str:
    """The start, some pages (at most five) or a section of one document, each page labelled ``[p.N]``."""
    found = documents(user, attachment_ids=[attachment_id])
    if not found:
        return f"No document {attachment_id} that you can open."
    doc = found[0]
    if doc.status != DocumentStatus.READY.value:
        return f"{doc.filename} {NOT_READY.get(doc.status, 'is not ready')}."
    count = doc.page_count or 1
    if section:
        match = find(doc.outline or [], section)
        if match is None:
            titles = ", ".join(label(s) for s in (doc.outline or []) if s.get("level") == 1) or "none"
            return f"No section {section!r} in {doc.filename}. Its top-level sections: {titles}."
        numbers = list(range(match["page_start"], match["page_end"] + 1))
        more = f" (the section runs to p.{match['page_end']})" if len(numbers) > MAX_PAGES else ""
        return f"{doc.filename}, {label(match)}{more}:\n\n" + _labelled(doc.attachment_id, numbers[:MAX_PAGES])
    if pages:
        wanted = [p for p in dict.fromkeys(pages) if 1 <= p <= count][:MAX_PAGES]
        if not wanted:
            return f"{doc.filename} has {count} pages."
        return f"{doc.filename}:\n\n" + _labelled(doc.attachment_id, wanted)
    return f"{doc.filename} ({count} pages), from the start:\n\n" + _labelled(
        doc.attachment_id, list(range(1, min(count, MAX_PAGES) + 1)), START_CHARS
    )
