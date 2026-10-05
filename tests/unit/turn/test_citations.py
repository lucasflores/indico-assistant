"""Citations are checked against their page (spec 025, T035; real DB for the document)."""

from unittest.mock import patch

from indico.modules.attachments.models.attachments import AttachmentFile

from indico_assistant.services.turn.citations import Citation, markers, on_page, validate
from indico_assistant.tasks import indexing


def test_markers_parse():
    assert markers("Pile-up is in-time [p.21] and out-of-time [p. 22]; see [page 3], [pp.4-5] and [slide 7].") == [
        21,
        22,
        3,
        4,
        7,
    ]
    assert markers("no citations") == []


def test_a_quote_matches_whatever_the_spacing_case_and_line_breaks():
    page = "The so-called pile-\nup events, i.e. in-time\nand out-of-time pile-up, are shown."
    assert on_page("In-time and out-of-time pile-up", page)
    assert on_page("so-called pileup events", page)
    assert not on_page("pile-up is irrelevant", page)
    assert not on_page("  ", page)


def test_only_quotes_on_their_page_are_kept_with_a_link(
    db, dummy_user, dummy_event, create_attachment, fake_embedder, caplog
):
    caplog.set_level("INFO")
    attachment = create_attachment(dummy_user, dummy_event, title="Thesis")
    attachment.file = AttachmentFile(user=dummy_user, filename="thesis.md", content_type="text/plain")
    attachment.file.save(b"# Thesis\nPile-up comes in two kinds: in-time and out-of-time.")
    db.session.flush()
    with patch.object(indexing, "_vector_search_enabled", return_value=True):
        indexing.index_attachment(attachment, embedder=fake_embedder)
    kept = validate(
        dummy_user,
        [
            Citation(document=attachment.id, page=1, quote="a sentence the model made up"),
            Citation(document=attachment.id, page=1, quote="in-time and out-of-time"),
            Citation(document=attachment.id, page=1, quote="in-time and out-of-time"),  # (one per page)
            Citation(document=attachment.id, page=9, quote="Pile-up"),
            Citation(document=999999, page=1, quote="Pile-up"),
        ],
    )
    assert [(c["attachment_id"], c["filename"], c["page"]) for c in kept] == [(attachment.id, "thesis.md", 1)]
    assert kept[0]["url"].endswith("#page=1") and "/attachments/" in kept[0]["url"]
    assert "a sentence the model made up" in caplog.text


def test_a_marker_cites_the_one_document_the_turn_saw_that_page_of(
    db, dummy_user, dummy_event, create_attachment, fake_embedder
):
    from indico_assistant.services.turn.citations import from_markers

    attachment = create_attachment(dummy_user, dummy_event, title="Notes")
    attachment.file = AttachmentFile(user=dummy_user, filename="notes.md", content_type="text/plain")
    attachment.file.save(b"# Notes\nThe budget was approved.")
    db.session.flush()
    with patch.object(indexing, "_vector_search_enabled", return_value=True):
        indexing.index_attachment(attachment, embedder=fake_embedder)
    text = "The budget was approved [p.1]; see also [p.4]."
    added = from_markers(text, {attachment.id: {1}}, [])
    assert [(c["attachment_id"], c["page"]) for c in added] == [(attachment.id, 1)]  # (p.4 was never seen)
    assert from_markers(text, {attachment.id: {1}, 999: {1}}, []) == []  # (two documents have a p.1: no guess)
    assert from_markers(text, {attachment.id: {1}}, [{"page": 1}]) == []  # (already cited)
