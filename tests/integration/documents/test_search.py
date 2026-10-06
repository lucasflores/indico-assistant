"""Hybrid search and reading, filtered by access (spec 025, T032; real DB)."""

from unittest.mock import MagicMock

import pytest
from indico.core.db.sqlalchemy.protection import ProtectionMode
from indico.modules.attachments.models.attachments import AttachmentFile

from indico_assistant.services.document import reader
from indico_assistant.services.document.search import search, tsquery
from indico_assistant.tasks import indexing


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(indexing, "_vector_search_enabled", lambda: True)


@pytest.fixture
def no_meaning():
    """An embedder with no signal: every text gets the same vector, so only the keyword channel can rank."""
    embedder = MagicMock()
    embedder.embed_text.side_effect = lambda _: [1.0] + [0.0] * 383
    embedder.embed_batch.side_effect = lambda texts: [[1.0] + [0.0] * 383 for _ in texts]
    return embedder


@pytest.fixture
def document(db, dummy_user, create_attachment, fake_embedder):
    def _document(event, content, filename="notes.md", embedder=fake_embedder, title="Notes"):
        attachment = create_attachment(dummy_user, event, title=title)
        attachment.file = AttachmentFile(user=dummy_user, filename=filename, content_type="text/plain")
        attachment.file.save(content.encode())
        db.session.flush()
        assert indexing.index_attachment(attachment, embedder=embedder)["status"] == "ready"
        return attachment

    return _document


FILLER = " ".join(f"Paragraph {i} discusses calorimeter showers in general terms." for i in range(60))


def test_an_exact_term_only_the_keyword_channel_finds_ranks_top_3(db, dummy_user, dummy_event, document, no_meaning):
    doc = document(
        dummy_event,
        f"# Report\n{FILLER}\n## Contracts\nThe board approved contract SC-2291.\n{FILLER}",
        embedder=no_meaning,
    )
    hits = search(dummy_user, "SC-2291", attachment_id=doc.id, embedder=no_meaning)
    assert any("SC-2291" in h.text for h in hits[:3])
    assert hits[0].filename == "notes.md" and hits[0].page == 1


def test_meaning_and_keywords_are_fused(db, dummy_user, dummy_event, document, fake_embedder):
    doc = document(
        dummy_event, "# Talk\nThe look-up table is stored as ROOT histograms.\n" + FILLER, embedder=fake_embedder
    )
    hits = search(dummy_user, 'where is the "look-up table" kept', attachment_id=doc.id, embedder=fake_embedder)
    assert "look-up table" in hits[0].text
    assert hits[0].score > hits[-1].score


def test_scope_by_document_and_event(db, dummy_user, dummy_event, create_event, document, fake_embedder):
    other_event = create_event(title="Other")
    mine = document(dummy_event, "Pile-up in this event.", embedder=fake_embedder)
    theirs = document(other_event, "Pile-up in the other event.", embedder=fake_embedder)
    assert {h.attachment_id for h in search(dummy_user, "pile-up", embedder=fake_embedder)} == {mine.id, theirs.id}
    assert {
        h.attachment_id for h in search(dummy_user, "pile-up", event_id=other_event.id, embedder=fake_embedder)
    } == {theirs.id}
    assert {h.attachment_id for h in search(dummy_user, "pile-up", attachment_id=mine.id, embedder=fake_embedder)} == {
        mine.id
    }


def test_documents_the_user_cannot_open_are_never_returned(
    db, dummy_user, create_user, create_event, document, fake_embedder
):
    outsider = create_user(2, email="outsider@example.test")
    secret_event = create_event(title="Board", protection_mode=ProtectionMode.protected)
    secret = document(secret_event, "The secret merger plan.", embedder=fake_embedder)
    assert search(outsider, "merger plan", embedder=fake_embedder) == []
    assert search(outsider, "merger plan", attachment_id=secret.id, embedder=fake_embedder) == []
    assert reader.read(outsider, secret.id, start=True) == f"No document {secret.id} that you can open."
    assert reader.documents(outsider, event_id=secret_event.id) == []
    secret_event.update_principal(outsider, read_access=True)
    db.session.flush()
    assert [h.attachment_id for h in search(outsider, "merger plan", embedder=fake_embedder)] == [secret.id]


def test_keyword_only_without_pgvector(db, dummy_user, dummy_event, document, monkeypatch):
    from indico_assistant.services.document import store

    monkeypatch.setattr(store, "_pgvector", False)
    doc = document(dummy_event, "Beam time was cut by two weeks.", embedder=None)
    assert [h.attachment_id for h in search(dummy_user, "beam time", attachment_id=doc.id)] == [doc.id]
    assert search(dummy_user, "the of and", attachment_id=doc.id) == []  # nothing to look for


def test_tsquery_is_an_or_of_words_with_phrases_kept():
    assert tsquery('What does the thesis say about "pile-up events" and ROOT?') == (
        "('pile-up' <-> 'events') | 'say' | 'root'"
    )
    assert tsquery("it's 4.4.1; DROP TABLE x") == "'4.4.1' | 'drop' | 'table'"


def test_reading_pages_sections_and_the_start(db, dummy_user, dummy_event, document):
    doc = document(
        dummy_event, "# Minutes\nIntro.\n## 1 Budget\nApproved.\n## 2 Travel\nFlights only.", title="Minutes"
    )
    start = reader.read(dummy_user, doc.id, start=True)
    assert start.startswith("notes.md (1 pages), from the start:") and "[p.1]" in start and "Flights only." in start
    assert "[p.1]" in reader.read(dummy_user, doc.id, pages=[1, 9])
    assert reader.read(dummy_user, doc.id, pages=[9]) == "notes.md has 1 pages."
    assert reader.read(dummy_user, doc.id, section="2").startswith("notes.md, 2 Travel:")
    assert "Its top-level sections: Minutes" in reader.read(dummy_user, doc.id, section="Appendix")
    listed = reader.describe(reader.documents(dummy_user, event_id=dummy_event.id)[0])
    assert listed == {
        "document": doc.id,
        "filename": "notes.md",
        "status": "ready",
        "pages": 1,
        "outline": ["Minutes (p.1)"],
    }


def test_a_document_not_ready_says_why(db, dummy_user, dummy_event, create_attachment):
    from indico_assistant.services.document import store

    attachment = create_attachment(dummy_user, dummy_event, title="Scan")
    store.queue(attachment)
    db.session.flush()
    assert reader.read(dummy_user, attachment.id, start=True) == (
        "dummy_file.txt is still being read; try again in a minute."
    )
    assert reader.describe(reader.documents(dummy_user, event_id=dummy_event.id)[0])["note"].startswith("is still")


def test_a_listing_shows_how_each_document_begins(db, dummy_user, dummy_event, document):
    doc = document(dummy_event, "Attention Is All You Need\nAshish Vaswani\nThe dominant sequence models...")
    [entry] = reader.describe_all(reader.documents(dummy_user, event_id=dummy_event.id))
    assert entry["document"] == doc.id and entry["begins"].startswith("Attention Is All You Need Ashish Vaswani")
