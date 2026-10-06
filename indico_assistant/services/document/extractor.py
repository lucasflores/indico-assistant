"""Reading a document's pages and the headings the file itself declares (spec 025, FR-010, research R3).

- **PDF:** pypdf, one text per page, NFKC-normalised (it restores the fi/ff ligatures), and the PDF outline.
- **Word:** python-docx; heading styles are headings, and Word's saved page breaks split the pages.
- **PowerPoint:** python-pptx, one page per slide; slide titles are headings.
- **Text and Markdown:** one page; Markdown's ``#`` lines are headings.

Documents without declared headings get numbered ones found in their text (``structure.py``).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md"}  # no .doc: python-docx can't read it
MAX_PAGES = 1000  # ponytail: bounds pathological files; the task's time limit bounds the rest


class ExtractionError(Exception):
    """The file could not be read."""


class UnsupportedFileTypeError(ExtractionError):
    """A type the plugin does not read."""


@dataclass
class Heading:
    """A heading the file declares (or that was found in its text)."""

    title: str
    level: int  # 1 = top
    page: int  # 1-based
    number: str | None = None  # "4.4.1"
    offset: int = 0  # where on the page it starts


@dataclass
class Extracted:
    pages: list[str]
    headings: list[Heading] = field(default_factory=list)


def clean(text: str) -> str:
    """NFKC (ligatures, full-width forms), without NULs and other control characters PostgreSQL or the chunker
    can't take. Line breaks and tabs stay: the heading finder reads lines."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(c for c in text if c.isprintable() or c in "\n\t")


def extract(path: str | Path, filename: str | None = None) -> Extracted:
    """The pages and declared headings of ``path``; its type comes from ``filename`` (or the path)."""
    ext = Path(filename or str(path)).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(f"Unsupported file type: {ext or 'none'}")
    reader = {".pdf": _pdf, ".docx": _docx, ".pptx": _pptx, ".txt": _text, ".md": _markdown}[ext]
    try:
        result = reader(Path(path))
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"Could not read {Path(filename or str(path)).name}: {exc}") from exc
    result.pages = [clean(p) for p in result.pages[:MAX_PAGES]]
    for h in result.headings:
        h.title = clean(h.title).strip()
    result.headings = [h for h in result.headings if h.title and h.page <= len(result.pages)]
    return result


def _pdf(path: Path) -> Extracted:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages[:MAX_PAGES]]
    headings: list[Heading] = []

    def walk(items: list[Any], level: int) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item, level + 1)
                continue
            try:
                index = reader.get_destination_page_number(item)
            except Exception:
                continue
            if index is not None and index >= 0:
                headings.append(Heading(title=str(item.title), level=level, page=index + 1))

    try:
        walk(reader.outline, 1)
    except Exception:
        logger.info("Unreadable outline in %s", path.name)
    for h in headings:
        number, title = _split_number(h.title)
        h.number, h.title = number, title
    return Extracted(pages, sorted(headings, key=lambda h: h.page))


def _split_number(title: str) -> tuple[str | None, str]:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)\.?\s+(.+)$", title)
    return (match.group(1), match.group(2)) if match else (None, title)


def _docx(path: Path) -> Extracted:
    from docx import Document

    pages: list[list[str]] = [[]]
    headings: list[Heading] = []
    for paragraph in Document(str(path)).paragraphs:
        if paragraph.contains_page_break and pages[-1]:  # Word saved where its pages broke: before this one
            pages.append([])
        text = clean(paragraph.text).strip()  # (cleaned first: the heading offsets are on the stored text)
        if text:
            style = paragraph.style.name if paragraph.style is not None else ""
            level = re.match(r"Heading (\d)", style or "")
            if level or style == "Title":
                number, title = _split_number(text)
                offset = sum(len(t) + 2 for t in pages[-1])
                headings.append(Heading(title, int(level.group(1)) if level else 1, len(pages), number, offset))
            pages[-1].append(text)
        if paragraph._p.xpath('.//w:br[@w:type="page"]') and pages[-1]:  # a typed page break: after this one
            pages.append([])
    if len(pages) > 1 and not pages[-1]:
        pages.pop()
    return Extracted(["\n\n".join(p) for p in pages], headings)


def _pptx(path: Path) -> Extracted:
    from pptx import Presentation

    pages, headings = [], []
    for number, slide in enumerate(Presentation(str(path)).slides, 1):
        texts = []
        title = slide.shapes.title.text_frame.text.strip() if slide.shapes.title is not None else ""
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                texts.append(shape.text_frame.text.strip())
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                texts.append(f"Notes: {notes}")
        pages.append("\n\n".join(texts))
        if title:
            headings.append(Heading(title=title, level=1, page=number))
    return Extracted(pages, headings)


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")  # never fails


def _text(path: Path) -> Extracted:
    return Extracted([_read_text(path)])


def _markdown(path: Path) -> Extracted:
    text = clean(_read_text(path))  # (cleaned first: the heading offsets are on the stored text)
    headings = []
    for match in re.finditer(r"^(#{1,6})\s+(.+?)\s*#*\s*$", text, re.MULTILINE):
        number, title = _split_number(match.group(2))
        headings.append(Heading(title, len(match.group(1)), 1, number, match.start()))
    return Extracted([text], headings)
