"""Unit tests for VectorStore duplicate detection.

Feature: 011-realtime-attachment-indexing
Tasks: T037

The store queries through ``ExtractedDocument.query``: that is what is mocked (mocking ``db.session`` left the
real query running against whatever database the config pointed at).
"""

from unittest.mock import Mock, call, patch

import pytest

from indico_assistant.services.vector_search.store import VectorStore


@pytest.fixture
def documents():
    with patch("indico_assistant.services.vector_search.store.ExtractedDocument") as model:
        yield model.query.filter_by


def test_a_new_document_is_not_a_duplicate(documents):
    documents.return_value.first.return_value = None
    assert VectorStore().check_duplicate_by_hash(event_id=123, content_hash="new_hash_not_in_db") is None


def test_an_existing_document_is_reported_with_its_chunk_count(documents):
    documents.return_value.first.return_value = Mock(attachment_id=99999, content_hash="existing_hash_abc123")
    documents.return_value.count.return_value = 15

    result = VectorStore().check_duplicate_by_hash(event_id=123, content_hash="existing_hash_abc123")

    assert result == {"attachment_id": 99999, "content_hash": "existing_hash_abc123", "chunk_count": 15}
    assert documents.call_args_list == [call(event_id=123, content_hash="existing_hash_abc123"),
                                        call(event_id=123, attachment_id=99999)]


def test_the_same_hash_in_another_event_is_not_a_duplicate(documents):
    documents.side_effect = lambda **kw: Mock(
        first=Mock(return_value=Mock(attachment_id=555, content_hash="shared_hash") if kw["event_id"] == 100
                   else None),
        count=Mock(return_value=3))
    store = VectorStore()
    assert store.check_duplicate_by_hash(event_id=100, content_hash="shared_hash") is not None
    assert store.check_duplicate_by_hash(event_id=200, content_hash="shared_hash") is None
