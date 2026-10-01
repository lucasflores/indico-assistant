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


def test_titles_parentheses_and_reference_links():
    """(review, PR #15) the forms of markdown link the regex missed or broke"""
    assert _check('[Admin](/admin/ "Admin page") and [Protection](/event/657/manage/protection "P")') == \
        f"Admin and [Protection]({BASE}/event/657/manage/protection)"
    assert _check('[evil](https://evil.com/x "t")') == "evil"
    assert _check("[Wiki](https://en.wikipedia.org/wiki/Pion_(particle)) and more") == "Wiki and more"
    assert _check("See [the page][1] and [tokens][2].\n\n[1]: /admin/\n[2]: /user/tokens/ \"Tokens\"") == \
        f"See [the page][1] and [tokens][2].\n\n\n[2]: {BASE}/user/tokens/"


def test_an_indico_under_a_path():
    """(review, PR #15) BASE_URL https://host/indico: paths are relative to it, never doubled"""
    base = "https://host/indico"
    assert check("[Manage](/event/657/manage/) [again](https://host/indico/event/657/manage/)", PAGES, GUIDE, base) == \
        f"[Manage]({base}/event/657/manage/) [again]({base}/event/657/manage/)"
    from indico_assistant.services.knowledge.links import found_in
    assert found_in(["[Sync](https://host/indico/event/657/)"], base)[0] == {"/event/657/"}


def test_text_without_links_is_unchanged():
    assert _check("Nothing to link here (really).") == "Nothing to link here (really)."


def test_menu_paths_are_relative_to_base_url(app, monkeypatch):
    """(review, PR #15) under BASE_URL https://host/indico, url_for gives /indico/...: the link check adds BASE_URL"""
    from types import SimpleNamespace

    from indico_assistant.services.knowledge import pages

    entry = SimpleNamespace(url="/indico/event/5/manage/", title="Settings")
    monkeypatch.setattr("indico.web.menu.build_menu_structure", lambda menu_id, **kwargs: [entry])
    with app.test_request_context(base_url="https://host/indico"):
        assert list(pages._menu("top-menu")) == [("", "Settings", "/event/5/manage/")]


# --- spec 023: a connector answer keeps only the GitHub addresses its tools returned (FR-017) ----------------

GITHUB = {"https://github.com/thoth-labs/indico-assistant/pull/16"}


def test_a_returned_github_address_is_kept_whatever_its_fragment():
    text = ("[#16](https://github.com/thoth-labs/indico-assistant/pull/16) and "
            "[a comment](https://github.com/thoth-labs/indico-assistant/pull/16#issuecomment-2)")
    assert check(text, PAGES, GUIDE, BASE, urls=GITHUB) == text


def test_any_other_link_loses_its_address_even_on_github():
    text = ("[#99](https://github.com/thoth-labs/indico-assistant/pull/99) "
            "[verify](https://evil.example/login) https://github.com/attacker/repo/issues/new?body=secret")
    assert check(text, PAGES, GUIDE, BASE, urls=GITHUB) == "#99 verify"


def test_images_are_dropped_to_their_text():
    from indico_assistant.services.knowledge.links import strip_images

    assert check(strip_images("![status](https://evil.example/c?q=private) ok"), PAGES, GUIDE, BASE) == "status ok"
    kept = check(strip_images("![#16](https://github.com/thoth-labs/indico-assistant/pull/16)"), PAGES, GUIDE, BASE,
                 urls=GITHUB)
    assert kept == "[#16](https://github.com/thoth-labs/indico-assistant/pull/16)"  # (a link now, not an image)


def test_an_image_is_neutralised_whatever_its_alt_text():
    """(Copilot, PR #17) nested brackets in the alt text slipped past a regex: now every image marker goes."""
    from indico_assistant.services.knowledge.links import strip_images

    for image in ("![a [b]](https://evil.example/?private)", "![a\\]b](https://evil.example/?p)", "![][1]"):
        assert "![" not in strip_images(image)
    text = check(strip_images("![a [b]](https://evil.example/?private) ok"), PAGES, GUIDE, BASE, urls=GITHUB,
                 strict=True)
    assert "evil.example" not in text and "![" not in text


def test_strict_mode_keeps_only_the_given_urls_and_this_indico():
    """(Copilot, PR #17) a connector answer has no use for Indico's docs site: it is not page-checked."""
    text = "[docs](https://docs.getindico.io/en/stable/?q=private) [#16](https://github.com/thoth-labs/indico-assistant/pull/16)"
    assert check(text, PAGES, GUIDE, BASE, urls=GITHUB, strict=True) == (
        "docs [#16](https://github.com/thoth-labs/indico-assistant/pull/16)")
    assert "docs.getindico.io" in check(text, PAGES, GUIDE, BASE, urls=GITHUB)  # (the knowledge answer keeps it)
