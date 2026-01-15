"""Pydantic schemas for session API request/response models.

Feature: 004-chat-api
Task: T003
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SessionListItem(BaseModel):
    """Single session item in the session list response.
    
    Attributes:
        session_id: Unique session identifier
        created_at: Session creation timestamp
        last_message_at: Timestamp of last message in session
        message_count: Total number of messages in session
        event_id: Optional event scope
    """
    
    session_id: UUID = Field(..., description="Session UUID")
    created_at: datetime = Field(..., description="Session creation time")
    last_message_at: datetime = Field(..., description="Last message timestamp")
    message_count: int = Field(..., ge=0, description="Number of messages")
    event_id: int | None = Field(default=None, description="Event scope (optional)")

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    """Response schema for GET /api/assistant/sessions.
    
    Attributes:
        sessions: List of session items
        total: Total number of sessions for the user
        limit: Requested limit
        offset: Requested offset
    """
    
    sessions: list[SessionListItem] = Field(
        default_factory=list,
        description="List of chat sessions"
    )
    total: int = Field(..., ge=0, description="Total session count")
    limit: int = Field(..., ge=1, le=100, description="Requested limit")
    offset: int = Field(..., ge=0, description="Requested offset")


class MessageItem(BaseModel):
    """Single message item in a session detail response.
    
    Attributes:
        message_id: Unique message identifier
        role: Message sender role ('user' or 'assistant')
        content: Message text content
        created_at: Message creation timestamp
        metadata: Additional message metadata (for assistant messages)
    """
    
    message_id: UUID = Field(..., description="Message UUID")
    role: Literal['user', 'assistant'] = Field(..., description="Message sender role")
    content: str = Field(..., description="Message content")
    created_at: datetime = Field(..., description="Message timestamp")
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Additional metadata (for assistant messages)"
    )

    model_config = {"from_attributes": True}


class SessionDetailResponse(BaseModel):
    """Response schema for GET /api/assistant/sessions/{session_id}.
    
    Attributes:
        session_id: Unique session identifier
        event_id: Optional event scope
        created_at: Session creation timestamp
        messages: List of messages in chronological order
    """
    
    session_id: UUID = Field(..., description="Session UUID")
    event_id: int | None = Field(default=None, description="Event scope (optional)")
    created_at: datetime = Field(..., description="Session creation time")
    messages: list[MessageItem] = Field(
        default_factory=list,
        description="Messages in chronological order"
    )

    model_config = {"from_attributes": True}


class SessionListQueryParams(BaseModel):
    """Query parameters for GET /api/assistant/sessions.
    
    Attributes:
        limit: Maximum number of sessions to return (1-100)
        offset: Number of sessions to skip
        event_id: Filter by event (optional)
    """
    
    limit: int = Field(default=20, ge=1, le=100, description="Page size")
    offset: int = Field(default=0, ge=0, description="Skip count")
    event_id: int | None = Field(default=None, description="Filter by event")
