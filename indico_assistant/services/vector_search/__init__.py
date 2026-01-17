"""Vector search service package for similarity search.

Feature: 006-vector-search-rag
Tasks: T012, T014

Provides vector storage, similarity search, and RAG integration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from indico.core.db import db as _db

logger = logging.getLogger(__name__)

# Cache for pgvector availability
_pgvector_available: bool | None = None


def check_pgvector_available(db: "_db" = None) -> bool:
    """Check if pgvector extension is available.
    
    Args:
        db: SQLAlchemy database session. If None, imports from indico.
        
    Returns:
        True if pgvector extension is available and usable.
    """
    global _pgvector_available
    
    if _pgvector_available is not None:
        return _pgvector_available
    
    if db is None:
        from indico.core.db import db
    
    try:
        result = db.session.execute(text(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        ))
        _pgvector_available = result.scalar()
        
        if _pgvector_available:
            logger.info("pgvector extension is available")
        else:
            logger.warning(
                "pgvector extension not found. "
                "Vector search will be disabled."
            )
        
        return _pgvector_available
        
    except Exception as e:
        logger.error(f"Error checking pgvector availability: {e}")
        _pgvector_available = False
        return False


def reset_pgvector_cache() -> None:
    """Reset the pgvector availability cache.
    
    Used mainly for testing.
    """
    global _pgvector_available
    _pgvector_available = None


# Import services after helper functions defined
from indico_assistant.services.vector_search.store import VectorStore
from indico_assistant.services.vector_search.search import SearchService
from indico_assistant.services.vector_search.rag import RAGService
from indico_assistant.services.vector_search.validation import (
    validate_graceful_degradation,
    validate_search_performance,
    validate_quickstart_scenarios,
    run_all_validations,
)

__all__ = [
    "check_pgvector_available",
    "reset_pgvector_cache",
    "VectorStore",
    "SearchService",
    "RAGService",
    "validate_graceful_degradation",
    "validate_search_performance",
    "validate_quickstart_scenarios",
    "run_all_validations",
]
