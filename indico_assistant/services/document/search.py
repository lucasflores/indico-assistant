"""Searching documents: keyword and meaning, fused (spec 025, FR-012, research R4).

One SQL statement ranks a scope's chunks twice, by ``ts_rank_cd`` over the keyword index (``simple``
configuration: events are multilingual) and by embedding distance, and fuses the two lists by reciprocal rank
(k = 60). The scope is filtered by access before anything is ranked: only documents whose attachment the user
can open, checked by Indico itself, as that user.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from indico.core.db import db
from indico.modules.attachments.models.attachments import Attachment
from sqlalchemy import text

from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.document import store

TOP = 8
DEPTH = 30  # candidates per channel
RRF_K = 60

_STOP = set("""a an and are as at be by can do does for from has have how i in is it its me my of on or our so
than that the their them then there these they this to was we were what when where which who why will with you
your about into page pages section document documents paper thesis talk slides""".split())


@dataclass
class Passage:
    attachment_id: int
    filename: str
    page: int
    section: str | None
    text: str
    score: float


def accessible(user: Any, attachment_ids: Iterable[int]) -> list[int]:
    """The attachments ``user`` can open, as Indico decides (``Attachment.can_access``), checked as that user:
    a protected contribution's check reads ``session.user``."""
    ids = sorted(set(attachment_ids))
    if not ids:
        return []
    with acting_as(user):
        attachments = Attachment.query.filter(Attachment.id.in_(ids), ~Attachment.is_deleted).all()
        return [a.id for a in attachments if not a.folder.is_deleted and a.can_access(user)]


def in_scope(*, attachment_id: int | None = None, event_id: int | None = None) -> list[int]:
    """Ready documents in a scope: one document, an event's, or (neither) every one."""
    sql = "SELECT attachment_id FROM plugin_assistant.documents WHERE status = 'ready'"
    if attachment_id is not None:
        sql += " AND attachment_id = :attachment_id"
    if event_id is not None:
        sql += " AND event_id = :event_id"
    rows = db.session.execute(text(sql), {"attachment_id": attachment_id, "event_id": event_id})
    return [row[0] for row in rows]


def tsquery(query: str) -> str:
    """The query as an OR of its words, quoted phrases kept together: a passage ranks by how much it holds."""
    parts = []
    for phrase in re.findall(r'["“”]([^"“”]{3,})["“”]', query):
        words = re.findall(r"[\w][\w\-.]*[\w]|\w", phrase.lower())
        if words:
            parts.append("(" + " <-> ".join(f"'{w}'" for w in words) + ")")
    query = re.sub(r'["“”][^"“”]{3,}["“”]', " ", query)
    for word in re.findall(r"[\w][\w\-.]*[\w]|\w", query.lower()):
        if word not in _STOP and len(word) > 1:
            parts.append(f"'{word}'")
    return " | ".join(dict.fromkeys(parts))


_SEARCH = """
WITH kw AS (
    SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.search, q) DESC, c.id) AS r
    FROM plugin_assistant.document_chunks c, to_tsquery('simple', :tsquery) q
    WHERE c.attachment_id = ANY(:ids) AND c.search @@ q
    ORDER BY r LIMIT :depth
), {vec}
ranked AS (
    SELECT id, sum(1.0 / (:k + r)) AS score FROM (SELECT * FROM kw {vec_union}) both_lists GROUP BY id
)
SELECT c.attachment_id, d.filename, c.page, c.section, c.text, ranked.score
FROM ranked
JOIN plugin_assistant.document_chunks c ON c.id = ranked.id
JOIN plugin_assistant.documents d ON d.attachment_id = c.attachment_id
ORDER BY ranked.score DESC, c.attachment_id, c.chunk_index
LIMIT :top
"""
_VEC = """vec AS (
    SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> CAST(:embedding AS vector), c.id) AS r
    FROM plugin_assistant.document_chunks c
    WHERE c.attachment_id = ANY(:ids) AND c.embedding IS NOT NULL
    ORDER BY r LIMIT :depth
),"""


def search(
    user: Any,
    query: str,
    *,
    attachment_id: int | None = None,
    event_id: int | None = None,
    embedder: Any = None,
    top: int = TOP,
) -> list[Passage]:
    """The best passages for ``query`` in the scope, among documents ``user`` can open."""
    ids = accessible(user, in_scope(attachment_id=attachment_id, event_id=event_id))
    terms = tsquery(query)
    if not ids or not (terms or embedder):
        return []
    embedding = None
    if embedder is not None and store.check_pgvector_available():
        embedding = "[" + ",".join(f"{x:.7g}" for x in embedder.embed_text(query)) + "]"
    sql = _SEARCH.format(vec=_VEC if embedding else "", vec_union="UNION ALL SELECT * FROM vec" if embedding else "")
    rows = db.session.execute(
        text(sql),
        {
            "ids": ids,
            "tsquery": terms or "''",
            "embedding": embedding,
            "depth": DEPTH,
            "k": RRF_K,
            "top": top,
        },
    )
    return [Passage(row[0], row[1], row[2], row[3], row[4], float(row[5])) for row in rows]
