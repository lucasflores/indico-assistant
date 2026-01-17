"""Embedding service package for vector search.

Feature: 006-vector-search-rag
Task: T008

Provides embedding generation using sentence-transformers.
"""

import logging

logger = logging.getLogger(__name__)

from indico_assistant.services.embedding.service import EmbeddingService
from indico_assistant.services.embedding.cache import EmbeddingCache

__all__ = [
    "EmbeddingService",
    "EmbeddingCache",
]
