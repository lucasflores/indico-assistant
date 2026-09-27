# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Unit tests for VectorStore service.

Feature: 007-tdd-gap-analysis (GAP-010)
Priority: HIGH
Coverage Target: ≥80%

Tests the vector storage functionality:
- Insert/retrieve/delete vectors
- Batch operations
- Similarity search
- Error handling
"""

import pytest
from unittest.mock import MagicMock, Mock, patch, PropertyMock
from uuid import uuid4
from contextlib import contextmanager, nullcontext

from indico_assistant.services.nl2sql.readonly_db import QueryContext
from indico_assistant.services.vector_search.store import VectorStore


class TestVectorStoreInit:
    """Tests for VectorStore initialization."""
    
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available')
    def test_init_with_pgvector(self, mock_check):
        """Test initialization when pgvector is available."""
        mock_check.return_value = True
        
        store = VectorStore()
        
        assert store._pgvector_available is True
        assert store.is_available is True
    
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available')
    def test_init_without_pgvector(self, mock_check):
        """Test initialization when pgvector is not available."""
        mock_check.return_value = False
        
        store = VectorStore()
        
        assert store._pgvector_available is False
        assert store.is_available is False


class TestVectorStoreInsertChunks:
    """insert_chunks: one multi-row INSERT with the vector bound (was INSERT + UPDATE per chunk)."""

    def _chunk(self, i=0, embedding=(0.5, 0.25)):
        return {"event_id": 1, "attachment_id": 100, "chunk_index": i, "content_text": f"Chunk {i}",
                "content_hash": "h" * 64, "embedding": list(embedding) if embedding else None,
                "metadata": {"file_id": 7}}

    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_insert_empty_chunks(self, mock_check, mock_db):
        assert VectorStore().insert_chunks([]) == 0
        mock_db.session.execute.assert_not_called()

    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_one_statement_for_all_chunks(self, mock_check, mock_db):
        assert VectorStore().insert_chunks([self._chunk(i) for i in range(5)]) == 5
        mock_db.session.execute.assert_called_once()
        sql, rows = mock_db.session.execute.call_args.args
        assert "CAST(:embedding AS vector)" in str(sql) and len(rows) == 5
        assert rows[0]["embedding"] == "[0.5,0.25]" and rows[0]["metadata"] == '{"file_id": 7}'
        mock_db.session.commit.assert_called_once()

    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=False)
    def test_without_pgvector_no_vector_column(self, mock_check, mock_db):
        VectorStore().insert_chunks([self._chunk(embedding=None)])
        assert "embedding" not in str(mock_db.session.execute.call_args.args[0]).split("VALUES")[0]

    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_replace_is_one_transaction(self, mock_check, mock_db):
        store = VectorStore()
        with patch.object(store, 'delete_attachment_chunks') as delete:
            store.replace_attachment_chunks(100, [self._chunk()])
        delete.assert_called_once_with(100, commit=False)
        mock_db.session.commit.assert_called_once()

class TestVectorStoreGetDocumentCount:
    """Tests for VectorStore.get_document_count method."""
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_get_document_count_all(self, mock_check, mock_doc_class, mock_db):
        """Test getting total document count."""
        store = VectorStore()
        
        mock_db.session.query.return_value.distinct.return_value.count.return_value = 42
        
        result = store.get_document_count()
        
        assert result == 42
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_get_document_count_by_event(self, mock_check, mock_doc_class, mock_db):
        """Test getting document count filtered by event."""
        store = VectorStore()
        
        mock_db.session.query.return_value.distinct.return_value.filter.return_value.count.return_value = 15
        
        result = store.get_document_count(event_id=1)
        
        assert result == 15
