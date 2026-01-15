"""FeedbackEntry model for user feedback on assistant responses.

Feature: 004-chat-api
Task: T008
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal, Union

from indico.core.db import db
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

if TYPE_CHECKING:
    from indico_assistant.models.message import ChatMessage


class FeedbackEntry(db.Model):
    """Represents user feedback on an assistant response.
    
    Users can provide different types of feedback on assistant messages:
    - thumbs_up/thumbs_down: Binary approval/disapproval
    - rating: 1-5 star rating
    - comment: Free-form text feedback
    
    A unique constraint ensures one feedback per type per user per message,
    allowing updates to existing feedback (upsert pattern).
    
    Attributes:
        id: Unique feedback identifier (UUID)
        message_id: Target message UUID
        user_id: User providing the feedback
        feedback_type: Type of feedback
        value: Feedback value (stored as TEXT)
        created_at: Feedback submission timestamp
        message: Relationship to parent ChatMessage
    """
    
    __tablename__ = 'feedback_entries'
    __table_args__ = {'schema': 'plugin_assistant'}

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey('plugin_assistant.chat_messages.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    user_id = Column(Integer, nullable=False, index=True)
    feedback_type = Column(
        String(32),
        nullable=False
    )  # thumbs_up, thumbs_down, rating, comment - CHECK constraint in migration
    value = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    message: "ChatMessage" = relationship(
        'ChatMessage',
        back_populates='feedback'
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<FeedbackEntry(id={self.id}, type={self.feedback_type}, "
            f"value={self.value})>"
        )

    @classmethod
    def create_or_update(
        cls,
        message_id: uuid.UUID,
        user_id: int,
        feedback_type: Literal['thumbs_up', 'thumbs_down', 'rating', 'comment'],
        value: Union[bool, int, str]
    ) -> "FeedbackEntry":
        """Create or update a feedback entry (upsert pattern).
        
        If feedback of the same type from the same user for the same
        message already exists, it will be updated. Otherwise, a new
        entry is created.
        
        Args:
            message_id: Target message UUID
            user_id: User providing feedback
            feedback_type: Type of feedback
            value: Feedback value (will be converted to string)
            
        Returns:
            Created or updated FeedbackEntry instance
        """
        # Convert value to string for storage
        str_value = str(value).lower() if isinstance(value, bool) else str(value)
        
        # Try to find existing feedback
        existing = cls.query.filter_by(
            message_id=message_id,
            user_id=user_id,
            feedback_type=feedback_type
        ).first()
        
        if existing:
            # Update existing feedback
            existing.value = str_value
            existing.created_at = datetime.now(timezone.utc)
            db.session.flush()
            return existing
        
        # Create new feedback
        feedback = cls(
            message_id=message_id,
            user_id=user_id,
            feedback_type=feedback_type,
            value=str_value
        )
        db.session.add(feedback)
        db.session.flush()
        return feedback

    @property
    def typed_value(self) -> Union[bool, int, str]:
        """Get the value in its appropriate Python type.
        
        Returns:
            bool for thumbs_up/thumbs_down, int for rating, str for comment
        """
        if self.feedback_type in ('thumbs_up', 'thumbs_down'):
            return self.value.lower() == 'true'
        elif self.feedback_type == 'rating':
            return int(self.value)
        return self.value
