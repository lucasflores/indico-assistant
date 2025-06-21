"""Utility functions for Indico Assistant."""

from typing import List, Dict, Any, Optional, Set
import os
from sentence_transformers import SentenceTransformer

# HuggingFace embedding model
EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")

def embed_text_huggingface(text: str) -> List[float]:
    """Get embeddings for text using HuggingFace Sentence Transformers."""
    return EMBEDDING_MODEL.encode(text).tolist()

def fetch_current_user_info() -> str:
    """Fetch current user information."""
    # TODO: Implement actual user info fetching
    return "Current user: admin"

def create_reference_footnotes(results: List[Dict[str, Any]]) -> Set[str]:
    """Create reference footnotes from query results."""
    footnotes = []
    for row in results:
        if all(k in row for k in ['event_id', 'event_title', 'event_start_dt', 'event_timezone']):
            footnotes.append(
                f"**Event Title**: *{row['event_title']}*, **Date/Time**: {row['event_start_dt']} {row['event_timezone']}, "
                f"**Event**: [http://localhost:8000/event/{row['event_id']}/](http://localhost:8000/event/{row['event_id']}/)"
            )
    return set(footnotes)
