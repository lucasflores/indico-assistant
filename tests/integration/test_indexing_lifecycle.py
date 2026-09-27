"""The document index follows attachments: upload, new version, clone, delete (real DB, fake embedder)."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from indico.modules.attachments.models.attachments import AttachmentFile, AttachmentType

from indico_assistant.services.document import DocumentProcessor
from indico_assistant.tasks import indexing, sync


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(indexing, '_vector_search_enabled', lambda: True)


@pytest.fixture
def embedder():
    embedder = MagicMock()
    embedder.embed_batch.side_effect = lambda texts: [[0.1] * 384 for _ in texts]
    return embedder


@pytest.fixture
def index(vector_store, embedder):
    def _index(attachment, force=False):
        return indexing.index_attachment(attachment, force=force,
                                         processor=DocumentProcessor(embedder, vector_store))
    return _index


@pytest.fixture
def attach(db, dummy_user, dummy_event, create_attachment):
    def _attach(title='Minutes', content=b'The committee approved the travel budget.'):
        attachment = create_attachment(dummy_user, dummy_event, title=title)
        new_version(db, attachment, content)
        return attachment
    return _attach


def chunks(db, attachment):
    return db.session.execute(text(
        "SELECT metadata_json->>'file_id', embedding IS NOT NULL FROM plugin_assistant.extracted_documents "
        "WHERE attachment_id = :id"), {'id': attachment.id}).fetchall()


def new_version(db, attachment, content):
    attachment.file = AttachmentFile(user=attachment.user, filename='minutes.txt', content_type='text/plain')
    attachment.file.save(content)
    db.session.flush()


def test_index_then_skip_while_current(db, index, attach, embedder):
    attachment = attach()
    assert index(attachment)['chunks_created'] >= 1
    assert chunks(db, attachment) and all(row == (str(attachment.file_id), True) for row in chunks(db, attachment))

    assert index(attachment)['error'] == 'current'  # decided from file_id alone
    assert embedder.embed_batch.call_count == 1


def test_new_file_version(db, index, attach, embedder):
    attachment = attach()
    index(attachment)
    new_version(db, attachment, b'The committee approved the travel budget.')  # same text
    assert index(attachment)['error'] == 'Content unchanged'
    assert {row[0] for row in chunks(db, attachment)} == {str(attachment.file_id)}
    assert embedder.embed_batch.call_count == 1

    new_version(db, attachment, b'The committee rejected the travel budget.')  # new text
    assert index(attachment)['chunks_created'] >= 1
    assert embedder.embed_batch.call_count == 2
    assert {row[0] for row in chunks(db, attachment)} == {str(attachment.file_id)}


def test_same_document_elsewhere_is_copied_not_embedded(db, index, attach, embedder):
    original, clone = attach('Minutes'), attach('Minutes (clone)')
    index(original)
    assert index(clone)['chunks_created'] == len(chunks(db, original))
    assert embedder.embed_batch.call_count == 1
    assert all(row == (str(clone.file_id), True) for row in chunks(db, clone))


def test_deleted_attachments_leave_the_index(db, index, attach):
    attachment = attach()
    index(attachment)
    attachment.is_deleted = True
    assert index(attachment)['error'] == 'deleted'
    assert chunks(db, attachment) == []


def test_links_are_never_indexed():
    link = MagicMock(is_deleted=False, folder=MagicMock(is_deleted=False), type=AttachmentType.link)
    assert indexing.skip_reason(link) == 'not a file'


def test_unsupported_or_disabled_is_not_indexed(db, index, attach, monkeypatch):
    image = attach()
    image.file.filename = 'photo.png'
    assert index(image)['error'] == 'unsupported format'
    monkeypatch.setattr(indexing, '_vector_search_enabled', lambda: False)
    assert index(attach())['error'] == 'vector search disabled'


def test_delete_signal_drops_chunks_in_the_same_transaction(db, index, attach):
    from indico_assistant.plugin import _on_attachment_deleted, _on_folder_deleted

    first, second = attach('a'), attach('b')
    index(first), index(second)
    _on_attachment_deleted(first)
    _on_folder_deleted(second.folder)
    assert chunks(db, first) == [] and chunks(db, second) == []


def test_changes_are_queued_only_after_commit(attach):
    from indico_assistant.plugin import _on_attachment_changed, _queue_pending_indexing

    attachment = attach()
    with patch.object(indexing.index_attachment_task, 'delay') as delay:
        _on_attachment_changed(attachment)
        _on_attachment_changed(attachment)  # created + updated in one request: queued once
        delay.assert_not_called()
        _queue_pending_indexing(None)
        _queue_pending_indexing(None)
    delay.assert_called_once_with(attachment.id)


def test_orphan_cleanup_and_stale_listing(db, index, attach):
    kept, gone, unindexed = attach('kept'), attach('gone'), attach('new')
    index(kept), index(gone)
    gone.is_deleted = True
    db.session.flush()
    assert sync.cleanup_orphaned_documents.run() ['deleted'] >= 1
    assert chunks(db, gone) == [] and chunks(db, kept)
    assert list(sync._attachment_ids(stale_only=True)) == [unindexed.id]
    assert set(sync._attachment_ids()) == {kept.id, unindexed.id}
