"""Feedback service for collecting user feedback on responses.

Feature: 004-chat-api
Task: T031
"""

from __future__ import annotations

import logging

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
        comment: Optional[str] = None,
        thumb_comment: Optional[str] = None
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
        # Verify message exists; locked, so concurrent votes on it cannot both switch thumbs
        message = ChatMessage.query.with_for_update().filter_by(id=message_id).first()
        if not message:
            raise MessageNotFoundError(f"Message {message_id} not found")
        
        # Verify user owns the session
        if not self._validate_message_access(message, user_id):
            raise MessageAccessDeniedError(
                "Cannot provide feedback on messages from other users' sessions"
            )
        
        # The model stores one value per (message, user, type); thumbs are one vote, so switching
        # between up and down replaces the other one.
        thumbs = ('thumbs_up', 'thumbs_down')
        if feedback_type in thumbs:
            FeedbackEntry.query.filter(
                FeedbackEntry.message_id == message_id,
                FeedbackEntry.user_id == user_id,
                FeedbackEntry.feedback_type.in_(thumbs),
                FeedbackEntry.feedback_type != feedback_type,
            ).delete(synchronize_session=False)
        value = {'rating': rating, 'comment': comment}.get(feedback_type, True)
        entry = FeedbackEntry.create_or_update(
            message_id=message_id,
            user_id=user_id,
            feedback_type=feedback_type,
            value=value if value is not None else '',
        )
        if feedback_type in thumbs:  # the turn keeps the vote: satisfaction outlives the chat (spec 024 FR-007)
            from indico_assistant.services.analytics import recorder
            recorder.rate(message_id, 1 if feedback_type == 'thumbs_up' else -1)
        if feedback_type in thumbs and thumb_comment and thumb_comment.strip():
            # the vote's comment, in the same transaction: a failure keeps neither (review, PR #5)
            FeedbackEntry.create_or_update(message_id=message_id, user_id=user_id, feedback_type='comment',
                                           value=thumb_comment.strip())
        return entry

    def withdraw_feedback(self, user_id: int, feedback_id: UUID) -> bool:
        """Take back a thumbs vote, and its comment (spec 020: the panel's thumb clicked again). False when the
        user has no such vote: someone else's is not theirs to take back."""
        entry = FeedbackEntry.query.filter_by(id=feedback_id, user_id=user_id).first()
        if entry is None:
            return False
        FeedbackEntry.query.filter(
            FeedbackEntry.message_id == entry.message_id,
            FeedbackEntry.user_id == user_id,
            FeedbackEntry.feedback_type.in_(('thumbs_up', 'thumbs_down', 'comment')),
        ).delete(synchronize_session=False)
        from indico_assistant.services.analytics import recorder
        recorder.rate(entry.message_id, None)  # (the thumbs went, whichever of the entries was named)
        return True

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
