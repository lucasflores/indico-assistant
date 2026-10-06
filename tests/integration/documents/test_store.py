"""Documents follow their attachments: status rows, new versions, deletes (spec 025, T031; real DB)."""

from unittest.mock import MagicMock, patch

import pytest
from indico.modules.attachments.models.attachments import AttachmentFile, AttachmentType
from sqlalchemy import text

from indico_assistant.models.document import Document
from indico_assistant.services.document import store
from indico_assistant.tasks import indexing, sync


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(indexing, "_vector_search_enabled", lambda: True)


@pytest.fixture
def read(fake_embedder):
    def _read(attachment, force=False):
        return indexing.index_attachment(attachment, force=force, embedder=fake_embedder)

    return _read


@pytest.fixture
def attach(db, dummy_user, dummy_event, create_attachment):
    def _attach(title="Minutes", content=b"The committee approved the travel budget.", filename="minutes.txt"):
        attachment = create_attachment(dummy_user, dummy_event, title=title)
        new_version(db, attachment, content, filename)
        return attachment

    return _attach


def new_version(db, attachment, content, filename="minutes.txt"):
    attachment.file = AttachmentFile(user=attachment.user, filename=filename, content_type="text/plain")
    attachment.file.save(content)
    db.session.flush()
    return attachment


def doc(attachment):
    return Document.query.get(attachment.id)


def chunks(db, attachment):
    return db.session.execute(
        text(
            "SELECT page, section, text, embedding IS NOT NULL FROM plugin_assistant.document_chunks "
            "WHERE attachment_id = :id ORDER BY chunk_index"
        ),
        {"id": attachment.id},
    ).fetchall()


def test_queued_then_read_to_ready(db, read, attach, fake_embedder):
    attachment = attach()
    store.queue(attachment)
    assert doc(attachment).status == "queued" and doc(attachment).file_id == attachment.file_id
    assert read(attachment)["status"] == "ready"
    d = doc(attachment)
    assert (d.status, d.page_count, d.filename, d.event_id) == ("ready", 1, "minutes.txt", attachment.folder.event_id)
    assert chunks(db, attachment) == [(1, None, "The committee approved the travel budget.", True)]
    assert read(attachment)["skipped"] == "current"  # decided from file_id alone
    assert fake_embedder.embed_batch.call_count == 1


def test_reading_is_visible_while_it_happens(db, read, attach, monkeypatch):
    attachment = attach()
    seen = []
    real = indexing._read
    monkeypatch.setattr(indexing, "_read", lambda a, e: seen.append(doc(a).status) or real(a, e))
    read(attachment)
    assert seen == ["reading"]


def test_sections_and_outline_are_stored(db, read, attach):
    attachment = attach(content=b"# Minutes\nintro\n## 1 Budget\nApproved.\n## 2 Travel\nFlights.", filename="m.md")
    read(attachment)
    assert [(s["number"], s["title"], s["level"]) for s in doc(attachment).outline] == [
        (None, "Minutes", 1),
        ("1", "Budget", 2),
        ("2", "Travel", 2),
    ]
    assert chunks(db, attachment)[0][1] == "Minutes"


def test_a_new_file_is_queued_and_read_again(db, read, attach, fake_embedder):
    attachment = attach()
    read(attachment)
    new_version(db, attachment, b"The committee rejected the travel budget.")
    store.queue(attachment)
    assert doc(attachment).status == "queued"
    read(attachment)
    assert doc(attachment).status == "ready" and "rejected" in chunks(db, attachment)[0][2]
    assert fake_embedder.embed_batch.call_count == 2


def test_the_same_file_keeps_its_status(db, read, attach):
    attachment = attach()
    read(attachment)
    attachment.title = "Renamed"
    store.queue(attachment)  # attachment_updated for a title edit
    assert doc(attachment).status == "ready"


def test_outcomes_other_than_ready(db, read, attach):
    blank = attach(content=b"   ")
    assert read(blank)["status"] == "no_text" and chunks(db, blank) == []
    sheet = attach(filename="budget.xlsx")
    assert read(sheet)["status"] == "unsupported" and doc(sheet).error == "unsupported format"
    broken = attach(content=b"%PDF-1.4 not really", filename="broken.pdf")
    assert read(broken)["status"] == "failed" and doc(broken).error


def test_a_newer_file_wins_over_a_slow_read(db, read, attach):
    attachment = attach()
    store.queue(attachment)
    db.session.commit()
    old_file = attachment.file_id
    new_version(db, attachment, b"Newer text.")
    store.queue(attachment)
    db.session.commit()
    assert store.write(attachment.id, old_file, 1, [], [], [], None) == 0  # the old read finished last
    assert doc(attachment).status == "queued"


def test_deleted_attachments_lose_their_document(db, read, attach):
    attachment = attach()
    read(attachment)
    attachment.is_deleted = True
    assert read(attachment)["skipped"] == "deleted"
    assert doc(attachment) is None and chunks(db, attachment) == []


def test_links_are_never_documents():
    link = MagicMock(is_deleted=False, folder=MagicMock(is_deleted=False), type=AttachmentType.link)
    assert indexing.skip_reason(link) == "not a file"


def test_disabled_reads_nothing(db, read, attach, monkeypatch):
    monkeypatch.setattr(indexing, "_vector_search_enabled", lambda: False)
    attachment = attach()
    assert read(attachment)["skipped"] == "disabled" and doc(attachment) is None


def test_delete_signals_drop_documents_in_the_same_transaction(db, read, attach):
    from indico_assistant.plugin import _on_attachment_deleted, _on_folder_deleted

    first, second = attach("a"), attach("b")
    read(first), read(second)
    _on_attachment_deleted(first)
    _on_folder_deleted(second.folder)
    assert doc(first) is None and doc(second) is None
    assert chunks(db, first) == [] and chunks(db, second) == []


def test_delete_signal_never_fails_indicos_delete(db, attach):
    from indico_assistant.plugin import _on_attachment_deleted

    attachment = attach()
    with patch.object(store, "delete", side_effect=RuntimeError("lock timeout")):
        _on_attachment_deleted(attachment)
    assert db.session.execute(text("SELECT 1")).scalar() == 1  # the outer transaction is still usable


def test_changes_are_queued_in_the_transaction_and_read_after_commit(attach):
    from indico_assistant.plugin import _on_attachment_changed, _queue_pending_indexing

    attachment = attach()
    with patch.object(indexing.index_attachment_task, "delay") as delay:
        _on_attachment_changed(attachment)
        _on_attachment_changed(attachment)  # created + updated in one request: queued once
        assert doc(attachment).status == "queued"
        delay.assert_not_called()
        _queue_pending_indexing(None)
        _queue_pending_indexing(None)
    delay.assert_called_once_with(attachment.id)


def test_orphan_cleanup_stuck_reads_and_stale_listing(db, read, attach):
    kept, gone, unread, stuck = attach("kept"), attach("gone"), attach("new"), attach("stuck")
    read(kept), read(gone)
    store.queue(stuck)
    db.session.flush()
    db.session.execute(
        text(
            "UPDATE plugin_assistant.documents SET status = 'reading', "
            "updated_at = now() - interval '2 hours' WHERE attachment_id = :id"
        ),
        {"id": stuck.id},
    )
    gone.is_deleted = True
    db.session.flush()
    result = sync.cleanup_orphaned_documents.run()
    assert result["deleted"] >= 1 and result["stuck"] == 1
    assert doc(gone) is None and doc(kept).status == "ready" and doc(stuck).status == "failed"
    assert set(sync._attachment_ids(stale_only=True)) == {unread.id, stuck.id}
    assert set(sync._attachment_ids()) == {kept.id, unread.id, stuck.id}


def test_status_counts(db, read, attach):
    read(attach())
    store.queue(attach())
    db.session.flush()
    assert store.status_counts() == {"ready": 1, "queued": 1}


def test_syncs_read_an_event_now_or_queue_what_is_stale(db, attach, dummy_event, monkeypatch, fake_embedder):
    monkeypatch.setattr(indexing, "_embedder", lambda: fake_embedder)
    first, second = attach("a"), attach("b", filename="sheet.xlsx")
    result = sync.sync_event_documents.run(dummy_event.id)
    assert result == {"success": True, "event_id": dummy_event.id, "statuses": {"ready": 1, "unsupported": 1}}
    assert sync.sync_event_documents.run(dummy_event.id)["statuses"] == {"current": 2}
    with patch.object(indexing.index_attachment_task, "delay") as delay:
        assert sync.sync_all_documents.run() == {"success": True, "attachments_queued": 0}
        assert sync.sync_all_documents.run(force=True)["attachments_queued"] == 2
    assert sorted(call.args[0] for call in delay.call_args_list) == sorted([first.id, second.id])


def test_no_outline_is_null_not_json_null(db, read, attach):
    sheet = attach(filename="budget.xlsx")
    read(sheet)
    assert db.session.execute(
        text("SELECT outline IS NULL FROM plugin_assistant.documents WHERE attachment_id = :id"), {"id": sheet.id}
    ).scalar()
