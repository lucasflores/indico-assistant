"""Pydantic schemas for chat API request/response models.

Feature: 004-chat-api
Task: T002
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request schema for POST /api/assistant/chat.
    
    Attributes:
        message: The user's natural language question (1-10,000 chars)
        session_id: Optional UUID to continue an existing session
        event_id: Optional event ID to scope queries to a specific event
    """
    
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="User's message to the assistant"
    )
    session_id: UUID | None = Field(
        default=None,
        description="Continue an existing session (optional)"
    )
    event_id: int | None = Field(
        default=None,
        description="Scope queries to a specific event (optional)"
    )


class ChatResponse(BaseModel):
    """Response schema for POST /api/assistant/chat.
    
    Attributes:
        response: The assistant's response text
        session_id: Session UUID (existing or newly created)
        message_id: UUID of the assistant's response message
        metadata: Additional metadata about the response
    """
    
    response: str = Field(
        ...,
        description="Assistant's response text"
    )
    session_id: UUID = Field(
        ...,
        description="Session UUID (existing or newly created)"
    )
    message_id: UUID = Field(
        ...,
        description="UUID of the assistant's response message"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Additional metadata (sql_generated, confidence, data_sources). "
            "Feature 015: data_sources changed from list[str] to list[dict] "
            "containing citation objects with type, url, description fields."
        )
    )

    model_config = {"from_attributes": True}
