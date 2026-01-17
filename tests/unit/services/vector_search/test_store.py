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
    """Tests for VectorStore.insert_chunks method."""
    
    @pytest.fixture
    def store(self):
        """Create a store with mocked dependencies."""
        with patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True):
            with patch('indico_assistant.services.vector_search.store.db'):
                return VectorStore()
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_insert_empty_chunks(self, mock_check, mock_doc, mock_db):
        """Test inserting empty chunks list."""
        store = VectorStore()
        
        result = store.insert_chunks([])
        
        assert result == 0
        mock_db.session.add.assert_not_called()
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_insert_single_chunk(self, mock_check, mock_doc_class, mock_db):
        """Test inserting a single chunk."""
        store = VectorStore()
        
        mock_doc_instance = MagicMock()
        mock_doc_instance.id = uuid4()
        mock_doc_class.return_value = mock_doc_instance
        
        chunks = [{
            "event_id": 1,
            "attachment_id": 100,
            "chunk_index": 0,
            "content_text": "Test content",
            "content_hash": "abc123",
            "embedding": [0.1] * 384,
            "metadata": {"filename": "test.pdf"}
        }]
        
        result = store.insert_chunks(chunks)
        
        assert result == 1
        mock_db.session.add.assert_called_once()
        mock_db.session.commit.assert_called_once()
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_insert_multiple_chunks(self, mock_check, mock_doc_class, mock_db):
        """Test inserting multiple chunks."""
        store = VectorStore()
        
        mock_doc_instance = MagicMock()
        mock_doc_instance.id = uuid4()
        mock_doc_class.return_value = mock_doc_instance
        
        chunks = [
            {
                "event_id": 1,
                "attachment_id": 100,
                "chunk_index": i,
                "content_text": f"Chunk {i}",
                "content_hash": "abc123",
                "embedding": [0.1] * 384,
            }
            for i in range(5)
        ]
        
        result = store.insert_chunks(chunks)
        
        assert result == 5
        assert mock_db.session.add.call_count == 5
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=False)
    def test_insert_without_pgvector(self, mock_check, mock_doc_class, mock_db):
        """Test inserting chunks when pgvector not available."""
        store = VectorStore()
        
        mock_doc_instance = MagicMock()
        mock_doc_instance.id = uuid4()
        mock_doc_class.return_value = mock_doc_instance
        
        chunks = [{
            "event_id": 1,
            "attachment_id": 100,
            "chunk_index": 0,
            "content_text": "Test",
            "content_hash": "abc",
            "embedding": [0.1] * 384,
        }]
        
        result = store.insert_chunks(chunks)
        
        # Should still insert, just without embedding
        assert result == 1
        mock_db.session.add.assert_called_once()
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_insert_chunk_without_embedding(self, mock_check, mock_doc_class, mock_db):
        """Test inserting chunk without embedding."""
        store = VectorStore()
        
        mock_doc_instance = MagicMock()
        mock_doc_instance.id = uuid4()
        mock_doc_class.return_value = mock_doc_instance
        
        chunks = [{
            "event_id": 1,
            "attachment_id": 100,
            "chunk_index": 0,
            "content_text": "Test",
            "content_hash": "abc",
            # No embedding
        }]
        
        result = store.insert_chunks(chunks)
        
        assert result == 1
        # _set_embedding should not be called
        mock_db.session.execute.assert_not_called()


class TestVectorStoreDeleteChunks:
    """Tests for VectorStore delete methods."""
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_delete_attachment_chunks(self, mock_check, mock_doc_class, mock_db):
        """Test deleting chunks by attachment ID."""
        store = VectorStore()
        
        mock_query = MagicMock()
        mock_query.filter_by.return_value.delete.return_value = 3
        mock_doc_class.query = mock_query
        
        result = store.delete_attachment_chunks(attachment_id=100)
        
        assert result == 3
        mock_query.filter_by.assert_called_once_with(attachment_id=100)
        mock_db.session.commit.assert_called_once()
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_delete_event_chunks(self, mock_check, mock_doc_class, mock_db):
        """Test deleting chunks by event ID."""
        store = VectorStore()
        
        mock_query = MagicMock()
        mock_query.filter_by.return_value.delete.return_value = 10
        mock_doc_class.query = mock_query
        
        result = store.delete_event_chunks(event_id=1)
        
        assert result == 10
        mock_query.filter_by.assert_called_once_with(event_id=1)
        mock_db.session.commit.assert_called_once()


class TestVectorStoreGetContentHash:
    """Tests for VectorStore.get_content_hash method."""
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_get_content_hash_found(self, mock_check, mock_doc_class, mock_db):
        """Test getting content hash when document exists."""
        store = VectorStore()
        
        mock_doc = MagicMock()
        mock_doc.content_hash = "abc123hash"
        mock_doc_class.query.filter_by.return_value.first.return_value = mock_doc
        
        result = store.get_content_hash(attachment_id=100)
        
        assert result == "abc123hash"
        mock_doc_class.query.filter_by.assert_called_once_with(
            attachment_id=100,
            chunk_index=0
        )
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_get_content_hash_not_found(self, mock_check, mock_doc_class, mock_db):
        """Test getting content hash when document not found."""
        store = VectorStore()
        
        mock_doc_class.query.filter_by.return_value.first.return_value = None
        
        result = store.get_content_hash(attachment_id=999)
        
        assert result is None


class TestVectorStoreGetChunkCount:
    """Tests for VectorStore.get_chunk_count method."""
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_get_chunk_count_all(self, mock_check, mock_doc_class, mock_db):
        """Test getting total chunk count."""
        store = VectorStore()
        
        mock_doc_class.query.count.return_value = 100
        
        result = store.get_chunk_count()
        
        assert result == 100
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_get_chunk_count_by_event(self, mock_check, mock_doc_class, mock_db):
        """Test getting chunk count filtered by event."""
        store = VectorStore()
        
        mock_query = MagicMock()
        mock_query.filter_by.return_value.count.return_value = 25
        mock_doc_class.query = mock_query
        
        result = store.get_chunk_count(event_id=1)
        
        assert result == 25
        mock_query.filter_by.assert_called_once_with(event_id=1)
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_get_chunk_count_by_attachment(self, mock_check, mock_doc_class, mock_db):
        """Test getting chunk count filtered by attachment."""
        store = VectorStore()
        
        mock_query = MagicMock()
        mock_query.filter_by.return_value.filter_by.return_value.count.return_value = 5
        mock_doc_class.query = mock_query
        
        result = store.get_chunk_count(event_id=1, attachment_id=100)
        
        assert result == 5


class TestVectorStoreSimilaritySearch:
    """Tests for VectorStore.similarity_search method."""
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=False)
    def test_similarity_search_without_pgvector(self, mock_check, mock_db):
        """Test similarity search when pgvector not available."""
        store = VectorStore()
        
        result = store.similarity_search(
            query_embedding=[0.1] * 384,
            event_id=1
        )
        
        assert result == []
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_similarity_search_basic(self, mock_check, mock_db):
        """Test basic similarity search."""
        store = VectorStore()
        
        # Mock query result
        mock_row = MagicMock()
        mock_row.id = uuid4()
        mock_row.event_id = 1
        mock_row.attachment_id = 100
        mock_row.chunk_index = 0
        mock_row.content_text = "Test content"
        mock_row.metadata_json = {"filename": "test.pdf"}
        mock_row.similarity = 0.95
        
        mock_db.session.execute.return_value = [mock_row]
        
        result = store.similarity_search(
            query_embedding=[0.1] * 384,
            event_id=1,
            top_k=5,
            threshold=0.7
        )
        
        assert len(result) == 1
        assert result[0]["event_id"] == 1
        assert result[0]["attachment_id"] == 100
        assert result[0]["content_text"] == "Test content"
        assert result[0]["similarity"] == 0.95
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_similarity_search_with_event_ids(self, mock_check, mock_db):
        """Test similarity search with multiple event IDs."""
        store = VectorStore()
        
        mock_db.session.execute.return_value = []
        
        store.similarity_search(
            query_embedding=[0.1] * 384,
            event_ids=[1, 2, 3],
            top_k=10
        )
        
        # Verify execute was called
        mock_db.session.execute.assert_called_once()
        call_args = mock_db.session.execute.call_args
        params = call_args[0][1]
        assert params["event_ids"] == [1, 2, 3]
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_similarity_search_no_results(self, mock_check, mock_db):
        """Test similarity search with no matching results."""
        store = VectorStore()
        
        mock_db.session.execute.return_value = []
        
        result = store.similarity_search(
            query_embedding=[0.1] * 384,
            event_id=999
        )
        
        assert result == []
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_similarity_search_multiple_results(self, mock_check, mock_db):
        """Test similarity search returning multiple results."""
        store = VectorStore()
        
        mock_rows = []
        for i in range(3):
            mock_row = MagicMock()
            mock_row.id = uuid4()
            mock_row.event_id = 1
            mock_row.attachment_id = 100
            mock_row.chunk_index = i
            mock_row.content_text = f"Chunk {i}"
            mock_row.metadata_json = {}
            mock_row.similarity = 0.95 - (i * 0.05)
            mock_rows.append(mock_row)
        
        mock_db.session.execute.return_value = mock_rows
        
        result = store.similarity_search(
            query_embedding=[0.1] * 384,
            event_id=1,
            top_k=5
        )
        
        assert len(result) == 3
        # Results should maintain order (by similarity)
        assert result[0]["similarity"] >= result[1]["similarity"]
        assert result[1]["similarity"] >= result[2]["similarity"]


class TestVectorStoreGetStats:
    """Tests for VectorStore.get_stats method."""
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.ExtractionStatus')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_get_stats_basic(self, mock_check, mock_status, mock_doc_class, mock_db):
        """Test getting basic stats."""
        store = VectorStore()
        
        # Mock query methods
        mock_doc_class.query.count.return_value = 100
        mock_doc_class.query.filter_by.return_value.count.return_value = 25
        
        # Mock distinct query
        mock_db.session.query.return_value.distinct.return_value.count.return_value = 10
        
        # Mock indexed count
        mock_result = MagicMock()
        mock_result.scalar.return_value = 80
        mock_db.session.execute.return_value = mock_result
        
        # Mock status enum
        mock_status.__iter__ = lambda x: iter([
            MagicMock(value='pending'),
            MagicMock(value='completed'),
            MagicMock(value='failed'),
            MagicMock(value='skipped')
        ])
        
        result = store.get_stats()
        
        assert "total_documents" in result
        assert "total_chunks" in result
        assert "indexed" in result
        assert "pgvector_available" in result
        assert result["pgvector_available"] is True
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.ExtractionStatus')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=False)
    def test_get_stats_without_pgvector(self, mock_check, mock_status, mock_doc_class, mock_db):
        """Test getting stats when pgvector not available."""
        store = VectorStore()
        
        mock_doc_class.query.count.return_value = 50
        mock_doc_class.query.filter_by.return_value.count.return_value = 10
        mock_db.session.query.return_value.distinct.return_value.count.return_value = 5
        
        mock_status.__iter__ = lambda x: iter([])
        
        result = store.get_stats()
        
        assert result["pgvector_available"] is False
        assert result["indexed"] == 0
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.ExtractedDocument')
    @patch('indico_assistant.services.vector_search.store.ExtractionStatus')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_get_stats_with_event_filter(self, mock_check, mock_status, mock_doc_class, mock_db):
        """Test getting stats filtered by event."""
        store = VectorStore()
        
        mock_query = MagicMock()
        mock_query.filter_by.return_value = mock_query
        mock_query.count.return_value = 20
        mock_doc_class.query = mock_query
        
        mock_db.session.query.return_value.distinct.return_value.filter.return_value.count.return_value = 3
        
        mock_result = MagicMock()
        mock_result.scalar.return_value = 15
        mock_db.session.execute.return_value = mock_result
        
        mock_status.__iter__ = lambda x: iter([])
        
        result = store.get_stats(event_id=1)
        
        # Should have been called with event filter
        assert "total_chunks" in result


class TestVectorStoreSetEmbedding:
    """Tests for VectorStore._set_embedding method."""
    
    @patch('indico_assistant.services.vector_search.store.db')
    @patch('indico_assistant.services.vector_search.store.check_pgvector_available', return_value=True)
    def test_set_embedding_format(self, mock_check, mock_db):
        """Test that embedding is formatted correctly for SQL."""
        store = VectorStore()
        
        doc_id = uuid4()
        embedding = [0.1, 0.2, 0.3]
        
        store._set_embedding(doc_id, embedding)
        
        # Verify execute was called
        mock_db.session.execute.assert_called_once()
        
        # Check the parameters
        call_args = mock_db.session.execute.call_args
        params = call_args[0][1]
        
        assert params["id"] == str(doc_id)
        assert params["embedding"] == "[0.1,0.2,0.3]"


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
