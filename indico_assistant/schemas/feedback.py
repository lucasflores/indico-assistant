"""Pydantic schemas for feedback API request/response models.

Feature: 004-chat-api
Task: T004
"""

from __future__ import annotations

from typing import Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class FeedbackRequest(BaseModel):
    """Request schema for POST /api/assistant/feedback.
    
    Attributes:
        message_id: UUID of the message to provide feedback on
        feedback_type: Type of feedback (thumbs_up, thumbs_down, rating, comment)
        value: Feedback value (type depends on feedback_type)
    """
    
    message_id: UUID = Field(
        ...,
        description="UUID of the message to provide feedback on"
    )
    feedback_type: Literal['thumbs_up', 'thumbs_down', 'rating', 'comment'] = Field(
        ...,
        description="Type of feedback being submitted"
    )
    value: Union[bool, int, str] = Field(
        ...,
        description="Feedback value (bool for thumbs, int 1-5 for rating, str for comment)"
    )

    @field_validator('value')
    @classmethod
    def validate_value(cls, v, info):
        """Validate that value matches the feedback_type."""
        feedback_type = info.data.get('feedback_type')
        
        if feedback_type in ('thumbs_up', 'thumbs_down'):
            if not isinstance(v, bool):
                raise ValueError('Thumbs feedback requires boolean value')
        elif feedback_type == 'rating':
            if not isinstance(v, int):
                raise ValueError('Rating must be an integer')
            if not 1 <= v <= 5:
                raise ValueError('Rating must be between 1 and 5')
        elif feedback_type == 'comment':
            if not isinstance(v, str):
                raise ValueError('Comment must be a string')
            if not v.strip():
                raise ValueError('Comment cannot be empty')
        
        return v


class FeedbackResponse(BaseModel):
    """Response schema for POST /api/assistant/feedback.
    
    Attributes:
        feedback_id: UUID of the created/updated feedback entry
        message_id: UUID of the message the feedback is for
        feedback_type: Type of feedback submitted
        created_at: Timestamp when feedback was created
    """
    
    feedback_id: UUID = Field(..., description="Feedback entry UUID")
    message_id: UUID = Field(..., description="Message UUID")
    feedback_type: str = Field(..., description="Type of feedback submitted")
    created_at: str = Field(..., description="Timestamp when feedback was created")

    model_config = {"from_attributes": True}
