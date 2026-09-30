"""Every link in a knowledge answer is one the user can open (spec 022, FR-012 and FR-016)."""

from indico_assistant.services.knowledge.links import check

BASE = "http://127.0.0.1:8000"
PAGES = ["/event/657/", "/event/657/manage/", "/event/657/manage/protection", "/user/tokens/"]
GUIDE = {"https://learn.getindico.io/", "https://learn.getindico.io/meetings/timetable/"}


def _check(text):
    return check(text, PAGES, GUIDE, BASE)


def test_a_listed_page_is_rebased_onto_this_indico_whatever_host_was_written():
    assert _check("[Protection](https://indico.example.com/event/657/manage/protection)") == \
        f"[Protection]({BASE}/event/657/manage/protection)"
    assert _check("[Protection](/event/657/manage/protection)") == f"[Protection]({BASE}/event/657/manage/protection)"
    assert _check("see [settings](http://indico.cern.ch/event/657/manage)") == \
        f"see [settings]({BASE}/event/657/manage/)"  # the trailing slash as the menu has it


def test_another_sites_home_page_is_not_this_indicos():
    home = ["/", *PAGES]
    assert check("[Google](https://www.google.com/) or [Indico](https://getindico.io)", home, GUIDE, BASE) == \
        "Google or Indico"
    assert check("[Home](/) and [home](http://127.0.0.1:8000/)", home, GUIDE, BASE) == f"[Home]({BASE}/) and [home]({BASE}/)"


def test_a_page_not_in_the_list_becomes_plain_text():
    assert _check("Open [Registration](/event/657/manage/registration/) now.") == "Open Registration now."
    assert _check("Open [Protection](/event/999/manage/protection).") == "Open Protection."


def test_guide_links_must_be_real_pages():
    assert _check("[Timetable](https://learn.getindico.io/meetings/timetable/#adding-a-break)") == \
        "[Timetable](https://learn.getindico.io/meetings/timetable/#adding-a-break)"
    assert _check("[API tokens](https://learn.getindico.io/user/api/)") == "API tokens"


def test_admin_docs_are_kept():
    text = "[Plugins](https://docs.getindico.io/en/stable/installation/plugins/)"
    assert _check(text) == text


def test_bare_urls():
    assert _check(f"Go to {BASE}/user/tokens/ and create one.") == f"Go to {BASE}/user/tokens/ and create one."
    assert _check("Go to https://indico.example.com/user/tokens/ now.") == f"Go to {BASE}/user/tokens/ now."
    assert _check("See https://example.org/made-up for more.") == "See for more."


def test_text_without_links_is_unchanged():
    assert _check("Nothing to link here (really).") == "Nothing to link here (really)."
