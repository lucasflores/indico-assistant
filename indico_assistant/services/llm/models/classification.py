"""Classification models for query understanding.

This module contains Pydantic models for classifying user queries
and extracting structured information.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Entity(BaseModel):
    """Extracted entity from user query.
    
    Represents a named entity extracted from natural language input,
    with confidence scoring for extraction quality.
    
    Attributes:
        type: Entity type (person, event, room, date, etc.).
        value: The extracted value.
        confidence: Extraction confidence score (0.0-1.0).
    
    Example:
        >>> entity = Entity(
        ...     type="person",
        ...     value="John Smith",
        ...     confidence=0.95
        ... )
    """
    type: str = Field(description="Entity type (person, event, room, date, etc.)")
    value: str = Field(description="Extracted value")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.9,
        description="Extraction confidence (0.0-1.0)"
    )


class TimeRange(BaseModel):
    """Temporal constraint from user query.
    
    Represents a time range extracted from natural language input,
    supporting both ISO dates and relative expressions.
    
    Attributes:
        start: Start date/time (ISO format or relative like "today").
        end: End date/time (ISO format or relative like "next week").
    
    Example:
        >>> time_range = TimeRange(
        ...     start="2026-01-14",
        ...     end="2026-01-21"
        ... )
    """
    start: str | None = Field(
        default=None,
        description="Start date (ISO or relative like 'today')"
    )
    end: str | None = Field(
        default=None,
        description="End date (ISO or relative like 'next week')"
    )


class QueryClassification(BaseModel):
    """Classification of user natural language query.
    
    This model represents the structured understanding of a user's
    query, including intent, entities, temporal constraints, and filters.
    
    Attributes:
        intent: Primary intent (e.g., "search_events", "get_statistics").
        entities: List of extracted named entities.
        time_range: Temporal constraints if present.
        filters: Additional filter criteria extracted from query.
        confidence: Overall classification confidence (0.0-1.0).
    
    Example:
        >>> classification = QueryClassification(
        ...     intent="search_events",
        ...     entities=[Entity(type="person", value="John Smith", confidence=0.95)],
        ...     time_range=TimeRange(start="2026-01-14", end="2026-01-21"),
        ...     filters={"category": "workshop"},
        ...     confidence=0.92
        ... )
    """
    intent: str = Field(description="Primary query intent")
    entities: list[Entity] = Field(
        default_factory=list,
        description="Extracted named entities"
    )
    time_range: TimeRange | None = Field(
        default=None,
        description="Temporal constraints if present"
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional filter criteria"
    )
    confidence: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Overall classification confidence (0.0-1.0)"
    )
