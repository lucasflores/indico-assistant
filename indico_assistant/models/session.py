"""ChatSession model for conversation persistence.

Feature: 004-chat-api
Task: T006
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from indico.core.db import db
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

if TYPE_CHECKING:
    from indico_assistant.models.message import ChatMessage


class ChatSession(db.Model):
    """Represents a conversation thread between a user and the assistant.
    
    A session contains multiple messages and tracks when the conversation
    was started and last updated. Sessions can optionally be scoped to
    a specific Indico event.
    
    Attributes:
        id: Unique session identifier (UUID)
        user_id: Indico user ID who owns the session
        event_id: Optional event scope (NULL = global)
        created_at: Session creation timestamp
        updated_at: Last activity timestamp (used for 90-day cleanup)
        messages: Relationship to ChatMessage instances
    """
    
    __tablename__ = 'chat_sessions'
    __table_args__ = {'schema': 'plugin_assistant'}

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id = Column(Integer, nullable=False, index=True)
    event_id = Column(Integer, nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True
    )

    # Relationships
    messages: list["ChatMessage"] = relationship(
        'ChatMessage',
        back_populates='session',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='ChatMessage.created_at'
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<ChatSession(id={self.id}, user_id={self.user_id}, "
            f"event_id={self.event_id})>"
        )

    @classmethod
    def create(
        cls,
        user_id: int,
        event_id: Optional[int] = None
    ) -> "ChatSession":
        """Create a new chat session.
        
        Args:
            user_id: Indico user ID
            event_id: Optional event scope
            
        Returns:
            Newly created ChatSession instance
        """
        session = cls(user_id=user_id, event_id=event_id)
        db.session.add(session)
        db.session.flush()  # Get the generated UUID
        return session

    def touch(self) -> None:
        """Update the updated_at timestamp to current time.
        
        Call this when adding new messages to the session.
        """
        self.updated_at = datetime.now(timezone.utc)

    @property
    def message_count(self) -> int:
        """Get the total number of messages in this session."""
        return self.messages.count()

    @property
    def last_message_at(self) -> Optional[datetime]:
        """Get the timestamp of the last message, or created_at if no messages."""
        last_msg = self.messages.order_by(None).order_by(
            db.desc('created_at')
        ).first()
        return last_msg.created_at if last_msg else self.created_at
