"""Citations: each statement taken from a document names its page, and the quote must be on it (spec 025, FR-013).

The answer's text cites as ``[p.N]``; the answer also lists each citation as (document, page, quote). A citation
whose quote isn't on that page of that document is dropped and logged. The ones that hold go into the answer's
``metadata.citations`` with a link that opens the file at the page.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MARKER = re.compile(r"\[(?:p|pp|page|slide)\.?\s*(\d+)(?:\s*[-–]\s*\d+)?\]", re.I)


class Citation(BaseModel):
    document: int = Field(..., description="The document's id, as the tools gave it")
    page: int = Field(..., description="The page (or slide) the quote is on")
    quote: str = Field(..., description="A few words copied exactly from that page, backing the statement")


def markers(text: str) -> list[int]:
    """The page numbers cited in the text, in order."""
    return [int(n) for n in MARKER.findall(text or "")]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"-\s*\n\s*", "", text)  # a word broken across lines
    return re.sub(r"[\W_]+", " ", text).strip()


def on_page(quote: str, page_text: str) -> bool:
    """The quote is on the page, whatever the spacing, case, punctuation or line breaks."""
    q = _norm(quote)
    return bool(q) and q in _norm(page_text)


def validate(user: Any, citations: list[Citation]) -> list[dict[str, Any]]:
    """The citations that hold, for the answer's metadata: one per (document, page), in order, with a link to the
    file at that page. Only documents the user can open are cited."""
    from indico_assistant.models.document import Document
    from indico_assistant.services.document.reader import pages_text
    from indico_assistant.services.document.search import accessible

    allowed = set(accessible(user, {c.document for c in citations}))
    kept: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for c in citations:
        if (c.document, c.page) in seen:
            continue
        doc = Document.query.get(c.document) if c.document in allowed else None
        text = pages_text(c.document, [c.page]).get(c.page, "") if doc is not None else ""
        if doc is None or not on_page(c.quote, text):
            logger.warning("A citation was dropped: %r is not on p.%s of document %s", c.quote[:80], c.page, c.document)
            continue
        seen.add((c.document, c.page))
        kept.append(_entry(doc, c.page))
    return kept


def _entry(doc: Any, page: int) -> dict[str, Any]:
    from indico.modules.attachments.models.attachments import Attachment

    attachment = Attachment.get(doc.attachment_id)
    url = f"{attachment.absolute_download_url}#page={page}" if attachment is not None else None
    return {"attachment_id": doc.attachment_id, "filename": doc.filename, "page": page, "url": url}


def from_markers(text: str, pages_seen: dict[int, set[int]], kept: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Citations for the text's [p.N] markers that no checked citation covers, when exactly one document the turn
    read or searched has that page: the statement points to a page the turn actually saw (models paraphrase their
    quotes, and a paraphrase is dropped above)."""
    from indico_assistant.models.document import Document

    covered = {c["page"] for c in kept}
    added: list[dict[str, Any]] = []
    for page in dict.fromkeys(markers(text)):
        documents = [d for d, pages in pages_seen.items() if page in pages]
        if page in covered or len(documents) != 1:
            continue
        doc = Document.query.get(documents[0])
        if doc is not None:
            added.append(_entry(doc, page))
            covered.add(page)
    return added
