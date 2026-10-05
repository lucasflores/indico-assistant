"""A document's sections: declared headings, or numbered ones found in its text (spec 025, research R3).

Numbered headings ("4.4.1 Fit Quality Measure", or "Chapter 4" over its title) are found line by line. Contents
pages and numbered list items look the same, so:
- lines with dot leaders or a trailing page number are dropped, and so is any page with six or more candidates
  (a contents page);
- the headings kept are the longest chain in which each number follows the one before (4.3.7 → 4.4 → 4.4.1),
  stepping by at most 2, so a stray "5 Particle Position: ..." list item can't cut the chain;
- a chain shorter than three is no outline.
"""

from __future__ import annotations

import re
from typing import Any

from indico_assistant.services.document.extractor import Heading

_NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(\S.{1,118})$")
_CHAPTER = re.compile(r"^(?:Chapter|CHAPTER|Section|Part)\s+(\d{1,2})\s*$")
_CONTENTS_LINE = re.compile(r"(\.\s?){4,}|\s\d{1,4}$")
_CONTENTS_PAGE = 6  # candidates on one page
MIN_CHAIN = 3  # fewer is noise (a slide deck's footers), not an outline


def _candidates(pages: list[str]) -> list[tuple[tuple[int, ...], Heading]]:
    found = []
    for page_number, page in enumerate(pages, 1):
        on_page = []
        lines = page.split("\n")
        offset = 0
        for i, raw in enumerate(lines):
            line = raw.strip()
            chapter = _CHAPTER.match(line)
            numbered = None if chapter else _NUMBERED.match(line)
            if chapter and i + 1 < len(lines) and lines[i + 1].strip():
                number, title = chapter.group(1), lines[i + 1].strip()
            elif numbered and numbered.group(2)[0].isupper() and not _CONTENTS_LINE.search(numbered.group(2)):
                number, title = numbered.group(1), numbered.group(2).strip()
            else:
                offset += len(raw) + 1
                continue
            key = tuple(int(n) for n in number.split("."))
            on_page.append((key, Heading(title=title, level=len(key), page=page_number, number=number, offset=offset)))
            offset += len(raw) + 1
        if len(on_page) < _CONTENTS_PAGE:
            found.extend(on_page)
    return found


def _follows(a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    """``b`` can be the next heading after ``a``: a later number, one or two steps on at the level that changed,
    and any deeper levels starting at 1 or 2 (a heading or two may be missed)."""
    if b <= a:
        return False
    for level, (x, y) in enumerate(zip(a, b, strict=False)):
        if x != y:
            return y - x <= 2 and all(n <= 2 for n in b[level + 1 :])
    return all(n <= 2 for n in b[len(a) :])


def numbered_headings(pages: list[str]) -> list[Heading]:
    """The longest chain of numbered headings (dynamic programming over the candidates, in reading order)."""
    candidates = _candidates(pages)
    if not candidates:
        return []
    best = [1] * len(candidates)
    before = [-1] * len(candidates)
    for j, (b, hb) in enumerate(candidates):
        if len(b) == 1 and len(hb.title.split()) > 10:  # a chapter title, not a numbered sentence
            best[j] = 0
            continue
        for i in range(j):
            if best[i] and best[i] + 1 > best[j] and _follows(candidates[i][0], b):
                best[j], before[j] = best[i] + 1, i
    j = max(range(len(candidates)), key=lambda k: best[k])
    if best[j] < MIN_CHAIN:
        return []
    chain = []
    while j != -1:
        chain.append(candidates[j][1])
        j = before[j]
    return chain[::-1]


def outline(headings: list[Heading], page_count: int) -> list[dict[str, Any]]:
    """Sections with page ranges: each runs to the page where the next heading at its level or above starts
    (that page included: the section's last lines may be on it)."""
    sections = []
    for i, h in enumerate(headings):
        end = next((later.page for later in headings[i + 1 :] if later.level <= h.level), page_count)
        sections.append(
            {
                "number": h.number,
                "title": h.title,
                "level": h.level,
                "page_start": h.page,
                "page_end": max(h.page, min(end, page_count)),
                "offset": h.offset,
            }
        )
    return sections


def label(section: dict[str, Any]) -> str:
    return f"{section['number']} {section['title']}" if section.get("number") else section["title"]


def section_at(sections: list[dict[str, Any]], page: int, offset: int) -> str | None:
    """The innermost section a passage at (page, offset) sits in: the last heading that starts before it."""
    current = None
    for s in sections:
        if (s["page_start"], s["offset"]) <= (page, offset):
            current = s
        else:
            break
    return label(current) if current else None


def find(sections: list[dict[str, Any]], wanted: str) -> dict[str, Any] | None:
    """A section by number ("4.4.1") or title (case-insensitive; a prefix or a substring will do)."""
    wanted = wanted.strip().rstrip(".").lower()
    number = re.match(r"^(?:section|chapter|§)?\s*(\d+(?:\.\d+)*)\b", wanted)
    if number:
        for s in sections:
            if s.get("number") == number.group(1):
                return s
    for test in (lambda t: t == wanted, lambda t: t.startswith(wanted), lambda t: wanted in t):
        for s in sections:
            if test(s["title"].lower()) or test(label(s).lower()):
                return s
    return None
