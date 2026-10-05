"""Documents: one row per attachment, and the chunks it was read into (spec 025, story 2).

A document's status says how far reading it got, so "still being read" and "has no text" can be said plainly.
Chunks never cross a page and carry their section. The ``embedding`` column is added by the migration (it needs
pgvector); ``search`` is the keyword index of the title, the section and the text, written with the chunk.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from indico.core.db import db
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR


def _now() -> datetime:
    return datetime.now(UTC)


class DocumentStatus(StrEnum):
    """``queued`` → ``reading`` → one of the four outcomes."""

    QUEUED = "queued"
    READING = "reading"
    READY = "ready"
    NO_TEXT = "no_text"  # no text layer (a scan)
    FAILED = "failed"  # an exception, kept in ``error``
    UNSUPPORTED = "unsupported"  # a type the plugin can't read, or too large


class ProcessingTier(StrEnum):
    """File size tier for indexing (feature 011)."""

    FAST = "fast"  # <10MB
    BEST_EFFORT = "best_effort"  # 10-50MB
    REJECTED = "rejected"  # >50MB, not read


class Document(db.Model):  # type: ignore[misc]  # (Indico's models are untyped)
    """One attachment's document: its file version, status and outline."""

    __tablename__ = "documents"
    __table_args__ = {"schema": "plugin_assistant"}

    attachment_id = Column(Integer, primary_key=True, autoincrement=False)
    event_id = Column(Integer, nullable=False, index=True)
    file_id = Column(Integer, nullable=False)  # a new file version means reading it again
    filename = Column(Text, nullable=False)
    content_type = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default=DocumentStatus.QUEUED.value)
    error = Column(Text, nullable=True)  # why it failed (admins only)
    page_count = Column(Integer, nullable=True)  # pages, or slides
    outline = Column(JSONB, nullable=True)  # [{number, title, level, page_start, page_end}]
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    def __repr__(self) -> str:
        return f"<Document({self.attachment_id}, {self.filename!r}, {self.status})>"


class DocumentChunk(db.Model):  # type: ignore[misc]
    """About 1,000 characters of one page, with the section it sits in."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("attachment_id", "chunk_index"),
        Index("ix_document_chunks_search", "search", postgresql_using="gin"),
        {"schema": "plugin_assistant"},
    )

    id = Column(BigInteger, primary_key=True)
    attachment_id = Column(
        Integer,
        ForeignKey("plugin_assistant.documents.attachment_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    page = Column(Integer, nullable=False)
    offset = Column(Integer, nullable=False)  # where on the page it starts: pages are rebuilt from their chunks
    section = Column(Text, nullable=True)  # e.g. "4.4.1 Fit Quality Measure"
    text = Column(Text, nullable=False)
    search = Column(TSVECTOR, nullable=False)
