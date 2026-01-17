"""Unit tests for EmbeddingService.

Feature: 007-tdd-gap-analysis
GAP: GAP-001 (Critical - LLM Integration)
Tasks: T008-T013

Tests the embedding generation service including:
- Single text embedding generation
- Batch embedding generation  
- Error handling when LLM/model unavailable
- Embedding dimension validation
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import numpy as np

from indico_assistant.services.embedding.service import EmbeddingService, create_embedding_service


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    @pytest.fixture
    def mock_plugin(self):
        """Create mock plugin with default settings."""
        plugin = MagicMock()
        plugin.settings.get.side_effect = lambda key, default=None: {
            "embedding_model": "test-model",
            "embedding_dimensions": 384,
            "embedding_batch_size": 32,
            "vector_search_enabled": True,
        }.get(key, default)
        return plugin

    @pytest.fixture
    def mock_plugin_disabled(self):
        """Create mock plugin with vector search disabled."""
        plugin = MagicMock()
        plugin.settings.get.side_effect = lambda key, default=None: {
            "embedding_model": "test-model",
            "embedding_dimensions": 384,
            "embedding_batch_size": 32,
            "vector_search_enabled": False,
        }.get(key, default)
        return plugin

    @pytest.fixture
    def service(self, mock_plugin):
        """Create EmbeddingService instance with mocked plugin."""
        return EmbeddingService(mock_plugin)

    @pytest.fixture
    def mock_sentence_transformer(self):
        """Create mock SentenceTransformer model."""
        mock_model = MagicMock()
        # Return 384-dimension embeddings
        mock_model.encode.return_value = np.array([[0.1] * 384])
        return mock_model

    # =========================================================================
    # T009: test_create_embedding_success
    # =========================================================================
    
    def test_create_embedding_success(self, service, mock_sentence_transformer):
        """Test embed_text with valid input returns expected embedding vector."""
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_sentence_transformer
        ):
            # Act
            result = service.embed_text("Hello world")
            
            # Assert
            assert result is not None
            assert isinstance(result, list)
            assert len(result) == 384
            assert all(isinstance(x, float) for x in result)
            mock_sentence_transformer.encode.assert_called()

    def test_create_embedding_normalizes_output(self, service, mock_sentence_transformer):
        """Test that embeddings are normalized."""
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_sentence_transformer
        ):
            service.embed_text("test")
            
            # Verify normalize_embeddings=True was passed
            call_kwargs = mock_sentence_transformer.encode.call_args[1]
            assert call_kwargs.get("normalize_embeddings") is True

    # =========================================================================
    # T010: test_create_embedding_error_handling
    # =========================================================================

    def test_create_embedding_disabled_raises_error(self, mock_plugin_disabled):
        """Test embed_text raises RuntimeError when vector search is disabled."""
        service = EmbeddingService(mock_plugin_disabled)
        
        with pytest.raises(RuntimeError, match="Vector search is disabled"):
            service.embed_text("test")

    def test_create_embedding_model_load_failure(self, service):
        """Test embed_text handles model loading failure gracefully."""
        with patch(
            "sentence_transformers.SentenceTransformer",
            side_effect=Exception("Model not found")
        ):
            with pytest.raises(Exception, match="Model not found"):
                service.embed_text("test")

    def test_create_embedding_import_error(self, service):
        """Test embed_text handles missing sentence-transformers library."""
        with patch(
            "sentence_transformers.SentenceTransformer",
            side_effect=ImportError("No module named 'sentence_transformers'")
        ):
            with pytest.raises(ImportError):
                service.embed_text("test")

    def test_create_embedding_encode_failure(self, service, mock_sentence_transformer):
        """Test embed_text handles encoding failure."""
        mock_sentence_transformer.encode.side_effect = RuntimeError("CUDA out of memory")
        
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_sentence_transformer
        ):
            with pytest.raises(RuntimeError, match="CUDA out of memory"):
                service.embed_text("test")

    # =========================================================================
    # T011: test_batch_embedding
    # =========================================================================

    def test_batch_embedding_success(self, service, mock_sentence_transformer):
        """Test embed_batch with multiple texts returns list of embeddings."""
        mock_sentence_transformer.encode.return_value = np.array([
            [0.1] * 384,
            [0.2] * 384,
            [0.3] * 384,
        ])
        
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_sentence_transformer
        ):
            texts = ["text1", "text2", "text3"]
            result = service.embed_batch(texts)
            
            assert len(result) == 3
            assert all(len(emb) == 384 for emb in result)
            assert all(isinstance(emb, list) for emb in result)

    def test_batch_embedding_empty_list(self, service):
        """Test embed_batch with empty list returns empty list."""
        result = service.embed_batch([])
        
        assert result == []

    def test_batch_embedding_single_item(self, service, mock_sentence_transformer):
        """Test embed_batch with single item works correctly."""
        mock_sentence_transformer.encode.return_value = np.array([[0.1] * 384])
        
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_sentence_transformer
        ):
            result = service.embed_batch(["single text"])
            
            assert len(result) == 1
            assert len(result[0]) == 384

    def test_batch_embedding_uses_batch_size(self, service, mock_sentence_transformer):
        """Test embed_batch respects batch_size setting."""
        mock_sentence_transformer.encode.return_value = np.array([[0.1] * 384])
        
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_sentence_transformer
        ):
            service.embed_batch(["text"])
            
            call_kwargs = mock_sentence_transformer.encode.call_args[1]
            assert call_kwargs.get("batch_size") == 32

    def test_batch_embedding_disabled_raises_error(self, mock_plugin_disabled):
        """Test embed_batch raises RuntimeError when vector search is disabled."""
        service = EmbeddingService(mock_plugin_disabled)
        
        with pytest.raises(RuntimeError, match="Vector search is disabled"):
            service.embed_batch(["test"])

    # =========================================================================
    # T012: test_embedding_dimensions
    # =========================================================================

    def test_embedding_dimensions_match_config(self, mock_plugin):
        """Test embedding dimensions match configured value."""
        service = EmbeddingService(mock_plugin)
        
        assert service.dimensions == 384

    def test_embedding_dimensions_auto_corrected(self, mock_plugin):
        """Test dimensions are auto-corrected if model returns different size."""
        mock_model = MagicMock()
        # Model returns 768-dim embeddings instead of configured 384
        mock_model.encode.return_value = np.array([[0.1] * 768])
        
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_model
        ):
            service = EmbeddingService(mock_plugin)
            service._load_model()
            
            # Dimensions should be updated to actual model output
            assert service.dimensions == 768

    def test_embedding_model_name_property(self, service):
        """Test model_name property returns configured model."""
        assert service.model_name == "test-model"

    def test_embedding_is_enabled_property(self, service, mock_plugin_disabled):
        """Test is_enabled property reflects configuration."""
        assert service.is_enabled is True
        
        disabled_service = EmbeddingService(mock_plugin_disabled)
        assert disabled_service.is_enabled is False


class TestEmbeddingServiceHealthCheck:
    """Tests for EmbeddingService.health_check()."""

    @pytest.fixture
    def mock_plugin(self):
        """Create mock plugin with default settings."""
        plugin = MagicMock()
        plugin.settings.get.side_effect = lambda key, default=None: {
            "embedding_model": "test-model",
            "embedding_dimensions": 384,
            "embedding_batch_size": 32,
            "vector_search_enabled": True,
        }.get(key, default)
        return plugin

    def test_health_check_healthy(self, mock_plugin):
        """Test health_check returns healthy status when model loads."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 384])
        
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_model
        ):
            service = EmbeddingService(mock_plugin)
            health = service.health_check()
            
            assert health["status"] == "healthy"
            assert health["model"] == "test-model"
            assert health["dimensions"] == 384
            assert health["error"] is None

    def test_health_check_disabled(self, mock_plugin):
        """Test health_check returns disabled status when service disabled."""
        mock_plugin.settings.get.side_effect = lambda key, default=None: {
            "embedding_model": "test-model",
            "embedding_dimensions": 384,
            "embedding_batch_size": 32,
            "vector_search_enabled": False,
        }.get(key, default)
        
        service = EmbeddingService(mock_plugin)
        health = service.health_check()
        
        assert health["status"] == "disabled"
        assert health["model"] is None

    def test_health_check_unhealthy(self, mock_plugin):
        """Test health_check returns unhealthy status on error."""
        with patch(
            "sentence_transformers.SentenceTransformer",
            side_effect=Exception("Model load failed")
        ):
            service = EmbeddingService(mock_plugin)
            health = service.health_check()
            
            assert health["status"] == "unhealthy"
            assert health["error"] == "Model load failed"


class TestCreateEmbeddingServiceFactory:
    """Tests for create_embedding_service factory function."""

    def test_factory_creates_service(self):
        """Test factory creates EmbeddingService instance."""
        mock_plugin = MagicMock()
        mock_plugin.settings.get.return_value = None
        
        service = create_embedding_service(mock_plugin)
        
        assert isinstance(service, EmbeddingService)
