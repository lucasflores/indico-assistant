"""Response summary models for natural language output.

This module contains Pydantic models for summarizing query results
in natural language format with confidence scoring.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResponseSummary(BaseModel):
    """Natural language response with confidence scoring.
    
    This model represents the final natural language response to
    a user query, including a confidence score and source tracking.
    
    Attributes:
        answer: Natural language response to the user.
        confidence: Confidence score (0.0-1.0) in the answer.
        sources: Data sources used to generate the answer.
    
    Example:
        >>> summary = ResponseSummary(
        ...     answer="There are 5 workshops scheduled for next week in Room A.",
        ...     confidence=0.92,
        ...     sources=["events.events", "events.contributions"]
        ... )
    """
    answer: str = Field(
        min_length=1,
        description="Natural language response"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0)"
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Data sources used"
    )
