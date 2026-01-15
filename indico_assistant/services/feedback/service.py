"""Feedback service for collecting user feedback on responses.

Feature: 004-chat-api
Task: T031
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from indico.core.db import db

from indico_assistant.models.feedback import FeedbackEntry
from indico_assistant.models.message import ChatMessage

logger = logging.getLogger(__name__)


class FeedbackServiceError(Exception):
    """Base exception for feedback service errors."""
    pass


class MessageNotFoundError(FeedbackServiceError):
    """Raised when the target message is not found."""
    pass


class MessageAccessDeniedError(FeedbackServiceError):
    """Raised when user doesn't own the message's session."""
    pass


class FeedbackService:
    """Service for managing user feedback on assistant responses.
    
    Handles creating, updating, and retrieving feedback entries
    for chat messages.
    """

    def submit_feedback(
        self,
        user_id: int,
        message_id: UUID,
        feedback_type: str,
        rating: Optional[int] = None,
        comment: Optional[str] = None
    ) -> FeedbackEntry:
        """Submit or update feedback for a message.
        
        If feedback already exists from this user for this message,
        it will be updated. Otherwise, a new entry is created.
        
        Args:
            user_id: Indico user ID
            message_id: Target message UUID
            feedback_type: Type of feedback (thumbs_up, thumbs_down, rating, etc.)
            rating: Optional numeric rating (1-5)
            comment: Optional text comment
            
        Returns:
            Created or updated FeedbackEntry
            
        Raises:
            MessageNotFoundError: If message doesn't exist
            MessageAccessDeniedError: If user doesn't own the session
        """
        # Verify message exists
        message = ChatMessage.query.get(message_id)
        if not message:
            raise MessageNotFoundError(f"Message {message_id} not found")
        
        # Verify user owns the session
        if not self._validate_message_access(message, user_id):
            raise MessageAccessDeniedError(
                "Cannot provide feedback on messages from other users' sessions"
            )
        
        # Check for existing feedback from this user on this message
        existing = FeedbackEntry.query.filter_by(
            message_id=message_id,
            user_id=user_id
        ).first()
        
        if existing:
            # Update existing feedback
            existing.feedback_type = feedback_type
            existing.rating = rating
            existing.comment = comment
            existing.updated_at = datetime.now(timezone.utc)
            db.session.flush()
            return existing
        
        # Create new feedback entry
        feedback = FeedbackEntry.create(
            message_id=message_id,
            user_id=user_id,
            feedback_type=feedback_type,
            rating=rating,
            comment=comment
        )
        
        return feedback

    def _validate_message_access(
        self,
        message: ChatMessage,
        user_id: int
    ) -> bool:
        """Validate user can provide feedback on a message.
        
        User must own the session containing the message.
        
        Args:
            message: Target message
            user_id: User ID to check
            
        Returns:
            True if user can provide feedback
        """
        session = message.session
        return session.user_id == user_id

    def get_feedback_for_message(
        self,
        message_id: UUID
    ) -> list[FeedbackEntry]:
        """Get all feedback for a message.
        
        Args:
            message_id: Message UUID
            
        Returns:
            List of FeedbackEntry
        """
        return FeedbackEntry.query.filter_by(message_id=message_id).all()

    def get_user_feedback(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> list[FeedbackEntry]:
        """Get all feedback from a user.
        
        Args:
            user_id: User ID
            limit: Maximum results
            offset: Skip count
            
        Returns:
            List of FeedbackEntry
        """
        return FeedbackEntry.query.filter_by(user_id=user_id)\
            .order_by(FeedbackEntry.created_at.desc())\
            .offset(offset)\
            .limit(limit)\
            .all()

    def commit(self) -> None:
        """Commit the current transaction."""
        db.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        db.session.rollback()


# Default instance
_feedback_service: FeedbackService | None = None


def get_feedback_service() -> FeedbackService:
    """Get or create the default feedback service instance.
    
    Returns:
        FeedbackService instance
    """
    global _feedback_service
    if _feedback_service is None:
        _feedback_service = FeedbackService()
    return _feedback_service
