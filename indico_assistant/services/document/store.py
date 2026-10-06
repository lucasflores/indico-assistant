"""Documents in the database: one status row per attachment, and its chunks (spec 025, research R5).

``queue`` writes the row in the upload's own transaction, so a document is "queued" from the moment its attachment
exists. The indexing task then marks it ``reading`` and writes the result: the chunks and ``ready`` together, or
one of ``no_text``, ``failed`` and ``unsupported``. A new file version sends the row back to ``queued``; deleting
the attachment deletes the row, and its chunks with it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from indico.core.db import db
from sqlalchemy import text

from indico_assistant.models.document import Document, DocumentStatus
from indico_assistant.services.document.chunker import keyword_text

logger = logging.getLogger(__name__)

DONE = {DocumentStatus.READY.value, DocumentStatus.NO_TEXT.value, DocumentStatus.UNSUPPORTED.value}

_pgvector: bool | None = None


def check_pgvector_available() -> bool:
    """Whether chunks have an embedding column: migration 012 adds it only where the ``vector`` extension was
    installed (cached per process). Without it, search is keyword-only."""
    global _pgvector
    if _pgvector is None:
        try:
            _pgvector = bool(
                db.session.execute(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = 'plugin_assistant'"
                        " AND table_name = 'document_chunks' AND column_name = 'embedding')"
                    )
                ).scalar()
            )
        except Exception:
            logger.exception("Could not check for pgvector")
            return False
        if not _pgvector:
            logger.warning("No embedding column (pgvector was not installed for migration 012): search is keyword-only")
    return _pgvector


def reset_pgvector_cache() -> None:
    global _pgvector
    _pgvector = None


def queue(attachment: Any) -> Document:
    """The status row for the attachment's current file, in the caller's transaction. A new file is queued again;
    the same file keeps its status (a title edit doesn't re-read anything)."""
    doc: Document | None = db.session.get(Document, attachment.id)
    if doc is None:
        doc = Document(attachment_id=attachment.id)
        db.session.add(doc)
    if doc.file_id != attachment.file_id:
        doc.file_id = attachment.file_id
        doc.status = DocumentStatus.QUEUED.value
        doc.error = doc.page_count = doc.outline = None
    doc.event_id = attachment.folder.event_id
    doc.filename = attachment.file.filename
    doc.content_type = attachment.file.content_type
    return doc


def is_current(attachment: Any) -> bool:
    """This file version was read to the end (or can't be)."""
    doc = db.session.get(Document, attachment.id)
    return doc is not None and doc.file_id == attachment.file_id and doc.status in DONE


def mark(attachment_id: int, file_id: int, status: DocumentStatus, error: str | None = None) -> None:
    """Set the status of this file version and commit, so the chat sees it at once. A newer file's row is left
    alone: its own task marks it."""
    Document.query.filter_by(attachment_id=attachment_id, file_id=file_id).update(
        {"status": status.value, "error": error}, synchronize_session="fetch"
    )
    db.session.commit()


def write(
    attachment_id: int,
    file_id: int,
    page_count: int,
    outline: list[dict[str, Any]],
    chunks: Sequence[Any],
    indexed: Sequence[str],
    embeddings: Sequence[Sequence[float]] | None,
) -> int:
    """Swap in the chunks and mark the document ready, in one transaction. Skipped (0) if a newer file arrived
    while this one was being read: its own task writes it."""
    doc = db.session.get(Document, attachment_id, with_for_update=True, populate_existing=True)
    if doc is None or doc.file_id != file_id:
        db.session.rollback()
        return 0
    db.session.execute(
        text("DELETE FROM plugin_assistant.document_chunks WHERE attachment_id = :id"), {"id": attachment_id}
    )
    vector = embeddings is not None and check_pgvector_available()
    rows = [
        {
            "attachment_id": attachment_id,
            "chunk_index": c.index,
            "page": c.page,
            "offset": c.offset,
            "section": c.section,
            "text": c.text,
            "indexed": keyword_text(indexed[i]),
            "embedding": "[" + ",".join(f"{x:.7g}" for x in embeddings[i]) + "]" if vector and embeddings else None,
        }
        for i, c in enumerate(chunks)
    ]
    if rows:
        db.session.execute(
            text(f"""
            INSERT INTO plugin_assistant.document_chunks
                (attachment_id, chunk_index, page, "offset", section, text, search{", embedding" if vector else ""})
            VALUES (:attachment_id, :chunk_index, :page, :offset, :section, :text, to_tsvector('simple', :indexed)
                    {", CAST(:embedding AS vector)" if vector else ""})
        """),
            rows,
        )
    doc.status, doc.error, doc.page_count, doc.outline = DocumentStatus.READY.value, None, page_count, outline
    db.session.commit()
    return len(rows)


def delete(attachment_ids: Sequence[int]) -> int:
    """Forget these attachments' documents (their chunks go with them). Doesn't commit: it runs in the deleting
    request's transaction."""
    if not attachment_ids:
        return 0
    result = db.session.execute(
        text("DELETE FROM plugin_assistant.documents WHERE attachment_id = ANY(:ids)"), {"ids": list(attachment_ids)}
    )
    return int(result.rowcount)


def status_counts() -> dict[str, int]:
    """Documents per status, for the health check."""
    rows = db.session.execute(text("SELECT status, count(*) FROM plugin_assistant.documents GROUP BY status"))
    return dict(rows.all())
