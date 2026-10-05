"""Page-bound chunks with their section (spec 025, T030)."""

import re

from indico_assistant.services.document.chunker import chunk_pages, indexed_text, join, split
from indico_assistant.services.document.structure import numbered_headings, outline

PAGES = [
    "Title page\nA thesis about calorimeters.",
    "1 Introduction\n" + " ".join(f"Sentence {i} about punch-through particles." for i in range(80)),
    "2 Method\nShort page.",
]


def test_chunks_never_cross_a_page_and_carry_their_section():
    sections = outline(numbered_headings(PAGES + ["3 Results\nx", "3.1 Fits\ny"]), 5)
    chunks = chunk_pages(PAGES, sections)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert {c.page for c in chunks} == {1, 2, 3}
    for c in chunks:
        assert c.text in PAGES[c.page - 1]
        assert PAGES[c.page - 1][c.offset :].startswith(c.text)
        assert len(c.text) <= 1000
    assert chunks[0].section is None
    assert {c.section for c in chunks if c.page == 2} == {"1 Introduction"}
    assert chunks[-1].section == "2 Method"
    assert sum(c.page == 2 for c in chunks) > 2  # a long page makes several


def test_pages_are_rebuilt_from_their_chunks():
    page = PAGES[1]
    assert join(split(page)) == page
    assert join(split("   padded   ")) == "padded"


def test_overlap_and_natural_breaks():
    pieces = split(PAGES[1])
    for (a, ta), (b, _) in zip(pieces, pieces[1:], strict=False):
        assert b < a + len(ta)  # they overlap
        assert re.search(r"[.]$", ta)  # broken after a sentence


def test_indexed_text_has_the_title_and_section_first():
    assert indexed_text("thesis.pdf", "4.4.1 Fit Quality Measure", "The chi2") == (
        "thesis.pdf\n4.4.1 Fit Quality Measure\nThe chi2"
    )
    assert indexed_text("notes.txt", None, "text") == "notes.txt\ntext"
