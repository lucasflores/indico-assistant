"""Session manager service for chat session CRUD operations.

Feature: 004-chat-api
Task: T014
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, tuple_

from indico.core.db import db
from indico.util.date_time import now_utc

from indico_assistant.models.message import ChatMessage
from indico_assistant.models.session import ChatSession


OPENING = timedelta(minutes=5)  # how long a conversation opened by the panel is listed before its first question


class InvalidCursor(ValueError):
    """A Past Chats page cursor this did not encode."""


class SessionManager:
    """Manages chat session lifecycle and message persistence.
    
    Provides CRUD operations for chat sessions and their messages,
    including session creation, message addition, and retrieval.
    """

    def create_session(
        self,
        user_id: int,
        event_id: Optional[int] = None,
        session_id: Optional[UUID] = None,
    ) -> ChatSession:
        """Create a new chat session.

        Args:
            user_id: Indico user ID
            event_id: The page it started on (information only, spec 020)
            session_id: The id to use: the Chainlit thread id (spec 020 R5); a new one when None

        Returns:
            Newly created ChatSession
        """
        if session_id is None:
            return ChatSession.create(user_id=user_id, event_id=event_id)
        # the panel's first question and Chainlit's naming of the thread (PUT /sessions/<id>) create it at the same
        # moment: whichever comes second finds it made (callers still check it is the user's)
        from sqlalchemy.dialects.postgresql import insert

        db.session.execute(insert(ChatSession.__table__)
                           .values(id=session_id, user_id=user_id, event_id=event_id)
                           .on_conflict_do_nothing(index_elements=['id']))
        return ChatSession.query.populate_existing().get(session_id)

    TITLE_CHARS = 60

    def title_of(self, session: ChatSession) -> str:
        """The name shown in Past Chats: the renamed title, else the start of the first question."""
        if session.title:
            return session.title
        first = (ChatMessage.query.filter_by(session_id=session.id, role='user')
                 .order_by(ChatMessage.created_at.asc()).first())
        return self.title_from(first.content if first else '')

    def title_from(self, text: str) -> str:
        """A question as a title: its start, cut at a word."""
        text = ' '.join((text or '').split())
        if len(text) <= self.TITLE_CHARS:
            return text
        return text[:self.TITLE_CHARS].rsplit(' ', 1)[0] + '…'

    def listed(self, user_id: int, search: str | None = None):
        """The user's conversations as Past Chats lists them, matching ``search``: one query for the pages and
        their total, so they always agree (review, PR #5)."""
        # a session the user said nothing in is not a conversation to go back to. One the panel opened for a
        # first question is, for the moments before the question is stored; if that question was refused (the
        # limits, an event it cannot see), it drops out (review, PR #5)
        query = ChatSession.query.filter(ChatSession.user_id == user_id,
                                         or_(ChatSession.messages.any(ChatMessage.role == 'user'),
                                             and_(ChatSession.title.isnot(None),
                                                  ChatSession.created_at > now_utc() - OPENING)))
        if search and (words := search.split()):
            # the user's % and _ are letters, not wildcards
            like = ['%' + w.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%' for w in words]
            has_word = [or_(ChatSession.title.ilike(w, escape='\\'),
                            ChatSession.messages.any(ChatMessage.content.ilike(w, escape='\\'))) for w in like]
            # ponytail: unindexed ILIKE over one user's (retention-bounded) messages; a trigram index if it grows
            query = query.filter(and_(*has_word))
        return query

    def page_sessions(self, user_id: int, limit: int = 20, cursor: Optional[str] = None,
                      search: Optional[str] = None) -> tuple[list[ChatSession], Optional[str]]:
        """A page of the user's sessions, last active first, and the cursor of the next page (None at the end).

        Keyset pagination on (updated_at, id): a session used between two pages moves to the top instead of
        shifting the pages under the reader (spec 020 R12).
        """
        query = self.listed(user_id, search)
        if cursor:
            updated_at, session_id = self._decode_cursor(cursor)
            query = query.filter(tuple_(ChatSession.updated_at, ChatSession.id) < tuple_(updated_at, session_id))
        rows = query.order_by(ChatSession.updated_at.desc(), ChatSession.id.desc()).limit(limit + 1).all()
        page = rows[:limit]
        next_cursor = self._encode_cursor(page[-1]) if len(rows) > limit else None
        return page, next_cursor

    @staticmethod
    def _encode_cursor(session: ChatSession) -> str:
        return base64.urlsafe_b64encode(f'{session.updated_at.isoformat()}|{session.id}'.encode()).decode()

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
        """Raises InvalidCursor for anything this did not encode (the cursor comes from the client)."""
        try:
            updated_at, session_id = base64.urlsafe_b64decode(cursor.encode()).decode().split('|')
            return datetime.fromisoformat(updated_at), UUID(session_id)
        except (ValueError, UnicodeError) as exc:  # (binascii.Error is a ValueError)
            raise InvalidCursor(cursor) from exc

    def summaries(self, sessions: list[ChatSession]) -> dict[UUID, tuple[int, datetime | None, str]]:
        """Per session of a page: message count, last message time and Past Chats title, in two queries
        (one per row each made a sidebar page cost ~3 queries a row)."""
        ids = [s.id for s in sessions]
        if not ids:
            return {}
        counts = {sid: (n, last) for sid, n, last in
                  db.session.query(ChatMessage.session_id, func.count(), func.max(ChatMessage.created_at))
                  .filter(ChatMessage.session_id.in_(ids)).group_by(ChatMessage.session_id)}
        untitled = [s.id for s in sessions if not s.title]
        firsts = dict(db.session.query(ChatMessage.session_id, ChatMessage.content)
                      .filter(ChatMessage.session_id.in_(untitled), ChatMessage.role == 'user')
                      .distinct(ChatMessage.session_id)
                      .order_by(ChatMessage.session_id, ChatMessage.created_at.asc())) if untitled else {}
        return {s.id: (counts.get(s.id, (0, None))[0], counts.get(s.id, (0, None))[1] or s.created_at,
                       s.title or self.title_from(firsts.get(s.id, '')))
                for s in sessions}

    def feedback_of(self, message_ids: list[UUID], user_id: int) -> dict[UUID, dict[str, Any]]:
        """The user's own latest thumbs (and comment) per message, as the panel shows them (spec 020 R11)."""
        from indico_assistant.models.feedback import FeedbackEntry

        found: dict[UUID, dict[str, Any]] = {}
        if not message_ids:
            return found
        entries = (FeedbackEntry.query
                   .filter(FeedbackEntry.message_id.in_(message_ids), FeedbackEntry.user_id == user_id)
                   .order_by(FeedbackEntry.created_at.asc()))
        for entry in entries:
            item = found.setdefault(entry.message_id, {'id': None, 'value': None, 'comment': None})
            if entry.feedback_type in ('thumbs_up', 'thumbs_down'):
                item['id'], item['value'] = str(entry.id), int(entry.feedback_type == 'thumbs_up')
            elif entry.feedback_type == 'comment':
                item['comment'] = entry.value
        return {message_id: item for message_id, item in found.items() if item['id'] is not None}

    def answer_id_of(self, message_id: UUID) -> UUID | None:
        """The id the question's answer is to be stored under (spec 020: the chat panel's run, which its thumbs
        vote on), unless a message has it already."""
        message = ChatMessage.query.get(message_id)
        wanted = (message.metadata_json or {}).get('answer_id') if message is not None else None
        if not wanted:
            return None
        wanted = UUID(wanted)
        return None if ChatMessage.query.get(wanted) is not None else wanted

    def page_event_of(self, message_id: UUID, fallback: int | None) -> int | None:
        """The event of the page a question was sent from (spec 020 R8). A question from before spec 020 has
        no page recorded: then the event its conversation started on."""
        message = ChatMessage.query.get(message_id)
        metadata = (message.metadata_json or {}) if message is not None else {}
        return metadata['event_id'] if 'event_id' in metadata else fallback

    def offer_before(self, session_id: UUID, message_id: UUID | None) -> str | None:
        """The change the last answer before the question ``message_id`` offered to make (spec 022 FR-005): the
        question then goes to the planner first, so a "yes" plans it."""
        question = ChatMessage.query.get(message_id) if message_id else None
        if question is None:
            return None
        last = (ChatMessage.query.filter(ChatMessage.session_id == session_id, ChatMessage.role == 'assistant',
                                         ChatMessage.created_at < question.created_at)
                .order_by(ChatMessage.created_at.desc()).first())
        return (((last.metadata_json or {}).get('route') or {}).get('offer') or None) if last else None

    def rename(self, session: ChatSession, title: str) -> None:
        """Rename a conversation, as the Past Chats sidebar does (spec 020 US4). Not a new activity: its
        place in the sidebar stays."""
        updated_at = session.updated_at
        session.title = title
        db.session.flush()
        session.updated_at = updated_at  # (onupdate would otherwise move it to the top)

    def set_message_metadata(self, message_id: UUID, **keys: Any) -> None:
        """Merge ``keys`` into a message's metadata."""
        message = ChatMessage.query.get(message_id)
        message.metadata_json = {**(message.metadata_json or {}), **keys}

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
        content: str,
        metadata: Optional[dict[str, Any]] = None
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
            content=content,
            metadata=metadata
        )
        session.touch()  # Update session timestamp
        return message

    def add_assistant_message(
        self,
        session: ChatSession,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        message_id: Optional[UUID] = None
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
            metadata=metadata,
            message_id=message_id
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

    def holds_connector_answer(self, session_id: UUID) -> bool:
        """Whether a GitHub (connector) answer is in this chat: it's in every later prompt (spec 024 FR-009)."""
        return db.session.query(ChatMessage.query.filter(
            ChatMessage.session_id == session_id, ChatMessage.role == "assistant",
            ChatMessage.metadata_json["route"]["route"].astext == "connector").exists()).scalar()

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
