"""Sections: declared or found in the text (spec 025, T029)."""

from indico_assistant.services.document.extractor import Heading
from indico_assistant.services.document.structure import find, label, numbered_headings, outline, section_at

# Modelled on the CERN thesis: a contents page, "Chapter N" over each chapter's title, numbered sections, and a
# numbered list item inside the text ("5 Particle Position: ...").
CONTENTS = "\n".join(
    [
        "Contents",
        "1 Introduction 1",
        "4 Calorimeter Punch-Through 21",
        "4.4 Parametrization . . . . . . . . 38",
        "4.4.1 Fit Quality Measure . . . . . 38",
        "4.4.2 Parametrization of Quantities . . . 39",
        "5 Implementation 59",
    ]
)
THESIS = [
    "Title page",
    CONTENTS,
    "Chapter 3\nDetector Simulation\nParticle physics might be the most fundamental approach.",
    "Chapter 4\nCalorimeter Punch-Through\nThis chapter defines punch-through.\n4.1 Calorimeter Punch-Through\n"
    "Leakage.\n4.2 Processes in the ATLAS Calorimeter\nShowers.",
    "4.3 Geant4 Analysis\nSome text.\n4.3.1 Simulation Setup\nMore text.",
    "Running header\n4.4 Parametrization\nIntro to the fits.\n4.4.1 Fit Quality Measure\nThe chi2 per bin.",
    "The steps are:\n5 Particle Position: From the recently computed deflection angles the position follows.\n"
    "6 Particle Momentum: The final step of the simulation computes the momentum.",
    "4.4.2 Parametrization of Quantities\nFits.",
    "Chapter 5\nImplementation\nThe code.",
    "5.1 Punch-Through Simulation\nDetails.",
]


def numbers(headings):
    return [(h.number, h.page) for h in headings]


def test_numbered_headings_skip_contents_and_list_items():
    found = numbered_headings(THESIS)
    assert numbers(found) == [
        ("3", 3),
        ("4", 4),
        ("4.1", 4),
        ("4.2", 4),
        ("4.3", 5),
        ("4.3.1", 5),
        ("4.4", 6),
        ("4.4.1", 6),
        ("4.4.2", 8),
        ("5", 9),
        ("5.1", 10),
    ]
    assert found[1].title == "Calorimeter Punch-Through"  # the line after "Chapter 4"
    fit = next(h for h in found if h.number == "4.4.1")
    assert fit.title == "Fit Quality Measure" and fit.level == 3
    assert THESIS[5][fit.offset :].startswith("4.4.1 Fit Quality Measure")


def test_a_short_chain_is_no_outline():
    assert numbered_headings(["Slide 1\n6 Fake lepton background estimation668", "6.1 The fake factor method"]) == []


def test_outline_page_ranges():
    sections = outline(numbered_headings(THESIS), len(THESIS))
    by_number = {s["number"]: s for s in sections}
    assert (by_number["4"]["page_start"], by_number["4"]["page_end"]) == (4, 9)
    assert (by_number["4.4.1"]["page_start"], by_number["4.4.1"]["page_end"]) == (6, 8)
    assert (by_number["5.1"]["page_start"], by_number["5.1"]["page_end"]) == (10, 10)
    assert all(1 <= s["page_start"] <= s["page_end"] <= len(THESIS) for s in sections)


def test_word_heading_levels_become_sections():
    headings = [
        Heading("Minutes", 1, 1),
        Heading("Budget", 2, 1, offset=10),
        Heading("Details", 3, 2),
        Heading("Actions", 2, 3),
    ]
    sections = outline(headings, 3)
    assert [(s["title"], s["level"], s["page_start"], s["page_end"]) for s in sections] == [
        ("Minutes", 1, 1, 3),
        ("Budget", 2, 1, 3),
        ("Details", 3, 2, 3),
        ("Actions", 2, 3, 3),
    ]


def test_section_at_a_position():
    sections = outline(numbered_headings(THESIS), len(THESIS))
    fit = THESIS[5].index("4.4.1")
    assert section_at(sections, 6, 0) == "4.3.1 Simulation Setup"  # the running header, before 4.4 starts
    assert section_at(sections, 6, fit - 5) == "4.4 Parametrization"
    assert section_at(sections, 6, fit + 30) == "4.4.1 Fit Quality Measure"
    assert section_at(sections, 1, 0) is None


def test_find_by_number_or_title():
    sections = outline(numbered_headings(THESIS), len(THESIS))
    assert label(find(sections, "4.4.1")) == "4.4.1 Fit Quality Measure"
    assert label(find(sections, "section 4.4")) == "4.4 Parametrization"
    assert label(find(sections, "fit quality")) == "4.4.1 Fit Quality Measure"
    assert label(find(sections, "Implementation")) == "5 Implementation"
    assert find(sections, "9.9") is None
