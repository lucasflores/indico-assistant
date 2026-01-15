"""Session manager service for chat session CRUD operations.

Feature: 004-chat-api
Task: T014
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from indico.core.db import db

from indico_assistant.models.message import ChatMessage
from indico_assistant.models.session import ChatSession


class SessionManager:
    """Manages chat session lifecycle and message persistence.
    
    Provides CRUD operations for chat sessions and their messages,
    including session creation, message addition, and retrieval.
    """

    def create_session(
        self,
        user_id: int,
        event_id: Optional[int] = None
    ) -> ChatSession:
        """Create a new chat session.
        
        Args:
            user_id: Indico user ID
            event_id: Optional event scope
            
        Returns:
            Newly created ChatSession
        """
        session = ChatSession.create(user_id=user_id, event_id=event_id)
        return session

    def get_session(self, session_id: UUID) -> Optional[ChatSession]:
        """Get a session by ID.
        
        Args:
            session_id: Session UUID
            
        Returns:
            ChatSession if found, None otherwise
        """
        return ChatSession.query.get(session_id)

    def get_session_or_create(
        self,
        session_id: Optional[UUID],
        user_id: int,
        event_id: Optional[int] = None
    ) -> tuple[ChatSession, bool]:
        """Get existing session or create new one.
        
        Args:
            session_id: Existing session UUID (or None)
            user_id: Indico user ID
            event_id: Optional event scope (for new sessions)
            
        Returns:
            Tuple of (ChatSession, created_flag)
        """
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session, False
        
        # Create new session
        session = self.create_session(user_id, event_id)
        return session, True

    def validate_session_ownership(
        self,
        session: ChatSession,
        user_id: int
    ) -> bool:
        """Check if user owns the session.
        
        Args:
            session: ChatSession to check
            user_id: User ID to verify
            
        Returns:
            True if user owns the session
        """
        return session.user_id == user_id

    def add_user_message(
        self,
        session: ChatSession,
        content: str
    ) -> ChatMessage:
        """Add a user message to a session.
        
        Args:
            session: Target session
            content: Message content
            
        Returns:
            Created ChatMessage
        """
        message = ChatMessage.create(
            session_id=session.id,
            role='user',
            content=content
        )
        session.touch()  # Update session timestamp
        return message

    def add_assistant_message(
        self,
        session: ChatSession,
        content: str,
        metadata: Optional[dict[str, Any]] = None
    ) -> ChatMessage:
        """Add an assistant message to a session.
        
        Args:
            session: Target session
            content: Message content
            metadata: Optional metadata (SQL, confidence, sources)
            
        Returns:
            Created ChatMessage
        """
        message = ChatMessage.create(
            session_id=session.id,
            role='assistant',
            content=content,
            metadata=metadata
        )
        session.touch()  # Update session timestamp
        return message

    def get_session_messages(
        self,
        session_id: UUID,
        limit: Optional[int] = None
    ) -> list[ChatMessage]:
        """Get all messages in a session.
        
        Args:
            session_id: Session UUID
            limit: Maximum messages to return (optional)
            
        Returns:
            List of ChatMessage in chronological order
        """
        query = ChatMessage.query.filter_by(session_id=session_id)\
            .order_by(ChatMessage.created_at.asc())
        
        if limit:
            query = query.limit(limit)
        
        return query.all()

    def list_user_sessions(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        event_id: Optional[int] = None
    ) -> list[ChatSession]:
        """List sessions for a user with pagination.
        
        Args:
            user_id: Indico user ID
            limit: Maximum sessions per page
            offset: Skip count for pagination
            event_id: Filter by event (optional)
            
        Returns:
            List of ChatSession ordered by last activity
        """
        query = ChatSession.query.filter_by(user_id=user_id)
        
        if event_id is not None:
            query = query.filter_by(event_id=event_id)
        
        # Get paginated results ordered by last activity
        sessions = query.order_by(ChatSession.updated_at.desc())\
            .offset(offset)\
            .limit(limit)\
            .all()
        
        return sessions

    def count_user_sessions(
        self,
        user_id: int,
        event_id: Optional[int] = None
    ) -> int:
        """Count total sessions for a user.
        
        Args:
            user_id: Indico user ID
            event_id: Filter by event (optional)
            
        Returns:
            Total number of sessions
        """
        query = ChatSession.query.filter_by(user_id=user_id)
        
        if event_id is not None:
            query = query.filter_by(event_id=event_id)
        
        return query.count()

    def delete_session(self, session_id: UUID) -> bool:
        """Delete a session by ID.
        
        Cascade delete removes associated messages and feedback.
        
        Args:
            session_id: Session UUID to delete
            
        Returns:
            True if session was deleted, False if not found
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        db.session.delete(session)
        db.session.flush()
        return True

    def commit(self) -> None:
        """Commit the current transaction."""
        db.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        db.session.rollback()


# Default instance
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get or create the default session manager instance.
    
    Returns:
        SessionManager instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
