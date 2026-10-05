"""Splitting a document's pages into chunks (spec 025, data-model ``document_chunks``).

Chunks are about 1,000 characters with a 200-character overlap, broken at a paragraph, line, sentence or word
near the limit (the study's setting). They never cross a page, and each carries the section it starts in. What is
embedded and keyword-indexed is the chunk prefixed with the document's title and the section (``indexed_text``):
contextual retrieval without model calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from indico_assistant.services.document.structure import section_at

SIZE = 1000
OVERLAP = 200
_SEPARATORS = ("\n\n", "\n", ". ", ", ", " ")


@dataclass
class Chunk:
    index: int
    page: int  # 1-based
    offset: int  # on the page
    section: str | None
    text: str


def _break(text: str, start: int, end: int, size: int) -> int:
    """A natural break in the last 100 characters before ``end`` (at least half a chunk in), else ``end``."""
    window = max(start + size // 2, end - 100)
    for separator in _SEPARATORS:
        position = text.rfind(separator, window, end)
        if position > start:
            return position + len(separator)
    return end


def split(text: str, size: int = SIZE, overlap: int = OVERLAP) -> list[tuple[int, str]]:
    """(offset, text) pieces of one page."""
    pieces = []
    start = 0
    while start < len(text):
        end = start + size
        if end >= len(text):
            end = len(text)
        else:
            end = _break(text, start, end, size)
        piece = text[start:end]
        if piece.strip():
            lead = len(piece) - len(piece.lstrip())
            pieces.append((start + lead, piece.strip()))
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return pieces


def chunk_pages(
    pages: list[str], sections: list[dict[str, Any]], size: int = SIZE, overlap: int = OVERLAP
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for number, page in enumerate(pages, 1):
        for offset, text in split(page, size, overlap):
            chunks.append(Chunk(len(chunks), number, offset, section_at(sections, number, offset), text))
    return chunks


def indexed_text(title: str, section: str | None, text: str) -> str:
    """What is embedded and keyword-indexed: the title and section give a passage its context."""
    return "\n".join(part for part in (title, section, text) if part)


def join(pieces: list[tuple[int, str]]) -> str:
    """A page again, from its (offset, text) chunks in order: each one's overlap with the one before is cut."""
    page = ""
    end = 0
    for offset, text in pieces:
        if not page:
            page, end = text, offset + len(text)
            continue
        if offset + len(text) <= end:
            continue
        page += text[end - offset :] if offset < end else "\n" + text
        end = offset + len(text)
    return page
