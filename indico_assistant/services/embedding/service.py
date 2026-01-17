"""Embedding service for generating vector embeddings.

Feature: 006-vector-search-rag
Tasks: T009, T010

Provides embedding generation using sentence-transformers library.
Default model: BAAI/bge-small-en-v1.5 (384 dimensions)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer
    from indico_assistant.plugin import AssistantPlugin

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating text embeddings using sentence-transformers.
    
    The embedding model is loaded lazily on first use to avoid startup delay
    when vector search is disabled.
    
    Attributes:
        _plugin: Reference to the AssistantPlugin for settings access.
        _model: Lazy-initialized SentenceTransformer model.
        _model_name: Name of the embedding model.
        _dimensions: Embedding vector dimensions.
    
    Example:
        >>> service = EmbeddingService(plugin)
        >>> embedding = service.embed_text("Hello world")
        >>> embeddings = service.embed_batch(["text1", "text2", "text3"])
    """
    
    def __init__(self, plugin: "AssistantPlugin") -> None:
        """Initialize embedding service with plugin reference.
        
        Args:
            plugin: The AssistantPlugin instance for settings access.
        
        Note:
            The actual model is NOT loaded here. It is lazy-initialized
            on first embed_text() or embed_batch() call.
        """
        self._plugin = plugin
        self._model: Optional["SentenceTransformer"] = None
        self._model_name: str = plugin.settings.get(
            "embedding_model", 
            "BAAI/bge-small-en-v1.5"
        )
        self._dimensions: int = plugin.settings.get("embedding_dimensions", 384)
        self._batch_size: int = plugin.settings.get("embedding_batch_size", 32)
        self._enabled: bool = plugin.settings.get("vector_search_enabled", True)
    
    @property
    def model_name(self) -> str:
        """Get the embedding model name."""
        return self._model_name
    
    @property
    def dimensions(self) -> int:
        """Get the embedding dimensions."""
        return self._dimensions
    
    @property
    def is_enabled(self) -> bool:
        """Check if vector search is enabled."""
        return self._enabled
    
    def _load_model(self) -> "SentenceTransformer":
        """Load the sentence-transformer model.
        
        Returns:
            Loaded SentenceTransformer model.
            
        Raises:
            ImportError: If sentence-transformers not installed.
            Exception: If model loading fails.
        """
        if self._model is not None:
            return self._model
        
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"Loading embedding model: {self._model_name}")
            self._model = SentenceTransformer(self._model_name)
            
            # Verify dimensions match expected
            test_embedding = self._model.encode(["test"], normalize_embeddings=True)
            actual_dims = test_embedding.shape[1]
            if actual_dims != self._dimensions:
                logger.warning(
                    f"Model dimensions ({actual_dims}) differ from configured "
                    f"({self._dimensions}). Using actual dimensions."
                )
                self._dimensions = actual_dims
            
            logger.info(
                f"Embedding model loaded: {self._model_name} "
                f"({self._dimensions} dimensions)"
            )
            return self._model
            
        except ImportError as e:
            logger.error(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    
    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text.
        
        Args:
            text: Text to embed.
            
        Returns:
            List of floats representing the embedding vector.
            
        Raises:
            RuntimeError: If vector search is disabled.
            Exception: If embedding generation fails.
        """
        if not self._enabled:
            raise RuntimeError("Vector search is disabled")
        
        model = self._load_model()
        
        try:
            embedding = model.encode(
                [text], 
                normalize_embeddings=True,
                show_progress_bar=False
            )
            return embedding[0].tolist()
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise
    
    def embed_batch(
        self, 
        texts: list[str],
        show_progress: bool = False
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed.
            show_progress: Whether to show progress bar.
            
        Returns:
            List of embedding vectors (list of floats each).
            
        Raises:
            RuntimeError: If vector search is disabled.
            Exception: If embedding generation fails.
        """
        if not self._enabled:
            raise RuntimeError("Vector search is disabled")
        
        if not texts:
            return []
        
        model = self._load_model()
        
        try:
            embeddings = model.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                show_progress_bar=show_progress
            )
            return [e.tolist() for e in embeddings]
        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            raise
    
    def health_check(self) -> dict[str, Any]:
        """Check embedding service health.
        
        Returns:
            Dictionary with health status and details.
        """
        if not self._enabled:
            return {
                "status": "disabled",
                "model": None,
                "dimensions": None,
                "error": None
            }
        
        try:
            model = self._load_model()
            return {
                "status": "healthy",
                "model": self._model_name,
                "dimensions": self._dimensions,
                "error": None
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "model": self._model_name,
                "dimensions": self._dimensions,
                "error": str(e)
            }


def create_embedding_service(plugin: "AssistantPlugin") -> EmbeddingService:
    """Factory function to create an EmbeddingService.
    
    Args:
        plugin: The AssistantPlugin instance.
        
    Returns:
        Configured EmbeddingService instance.
    """
    return EmbeddingService(plugin)
