"""ChatMessage model for conversation messages.

Feature: 004-chat-api
Task: T007
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal, Optional

from indico.core.db import db
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

if TYPE_CHECKING:
    from indico_assistant.models.feedback import FeedbackEntry
    from indico_assistant.models.session import ChatSession


class ChatMessage(db.Model):
    """Represents a single message in a conversation.
    
    Messages belong to a session and can be from either the user or the
    assistant. Assistant messages can include metadata such as generated
    SQL, confidence scores, and data sources.
    
    Attributes:
        id: Unique message identifier (UUID)
        session_id: Parent session UUID
        role: Message sender ('user' or 'assistant')
        content: Message text content (max 10,000 characters)
        metadata_json: Additional metadata for assistant messages
        created_at: Message creation timestamp
        session: Relationship to parent ChatSession
        feedback: Relationship to FeedbackEntry instances
    """
    
    __tablename__ = 'chat_messages'
    __table_args__ = {'schema': 'plugin_assistant'}

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey('plugin_assistant.chat_sessions.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    role = Column(
        String(16),
        nullable=False
    )  # 'user' or 'assistant' - CHECK constraint in migration
    content = Column(Text, nullable=False)
    metadata_json = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    # Relationships
    session: "ChatSession" = relationship(
        'ChatSession',
        back_populates='messages'
    )
    feedback: list["FeedbackEntry"] = relationship(
        'FeedbackEntry',
        back_populates='message',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self) -> str:
        """Return string representation."""
        content_preview = self.content[:50] + '...' if len(self.content) > 50 else self.content
        return (
            f"<ChatMessage(id={self.id}, role={self.role}, "
            f"content='{content_preview}')>"
        )

    @classmethod
    def create(
        cls,
        session_id: uuid.UUID,
        role: Literal['user', 'assistant'],
        content: str,
        metadata: Optional[dict[str, Any]] = None
    ) -> "ChatMessage":
        """Create a new chat message.
        
        Args:
            session_id: Parent session UUID
            role: 'user' or 'assistant'
            content: Message text content
            metadata: Optional metadata dict (for assistant messages)
            
        Returns:
            Newly created ChatMessage instance
        """
        message = cls(
            session_id=session_id,
            role=role,
            content=content,
            metadata_json=metadata
        )
        db.session.add(message)
        db.session.flush()  # Get the generated UUID
        return message

    @property
    def is_user_message(self) -> bool:
        """Check if this is a user message."""
        return self.role == 'user'

    @property
    def is_assistant_message(self) -> bool:
        """Check if this is an assistant message."""
        return self.role == 'assistant'

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get a metadata value by key.
        
        Args:
            key: Metadata key to retrieve
            default: Default value if key not found
            
        Returns:
            Metadata value or default
        """
        if self.metadata_json is None:
            return default
        return self.metadata_json.get(key, default)
