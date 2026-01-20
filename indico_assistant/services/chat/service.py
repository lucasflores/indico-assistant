"""Chat service orchestrator for processing user messages.

Coordinates the chat flow: session management, context building,
NL2SQL processing, and response generation.

Feature: 004-chat-api
Feature: 006-vector-search-rag (RAG integration T039, T040)
Task: T015
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from indico.core.db import db

from indico_assistant.models.message import ChatMessage
from indico_assistant.models.session import ChatSession
from indico_assistant.services.chat.context_builder import (
    ContextBuilder,
    get_context_builder,
)
from indico_assistant.services.chat.session_manager import (
    SessionManager,
    get_session_manager,
)

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    """Result of processing a chat message.
    
    Attributes:
        response: Assistant's response text
        session_id: Session UUID
        message_id: Assistant message UUID
        metadata: Response metadata (SQL, confidence, sources)
        created_session: Whether a new session was created
    """
    response: str
    session_id: UUID
    message_id: UUID
    metadata: dict[str, Any]
    created_session: bool = False


class ChatServiceError(Exception):
    """Base exception for chat service errors."""
    pass


class SessionNotFoundError(ChatServiceError):
    """Raised when a session is not found."""
    pass


class SessionAccessDeniedError(ChatServiceError):
    """Raised when user doesn't own the session."""
    pass


class EventAccessDeniedError(ChatServiceError):
    """Raised when user doesn't have access to the event."""
    
    def __init__(self, event_id: int, message: str = "Access denied"):
        self.event_id = event_id
        super().__init__(message)


class QueryProcessingError(ChatServiceError):
    """Raised when NL2SQL processing fails."""
    
    def __init__(self, message: str, reason: Optional[str] = None):
        self.reason = reason
        super().__init__(message)


class ChatService:
    """Orchestrates chat message processing.
    
    Coordinates between session management, context building, and
    the NL2SQL pipeline to process user messages and generate responses.
    """

    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        context_builder: Optional[ContextBuilder] = None
    ):
        """Initialize the chat service.
        
        Args:
            session_manager: Custom session manager (optional)
            context_builder: Custom context builder (optional)
        """
        self._session_manager = session_manager or get_session_manager()
        self._context_builder = context_builder or get_context_builder()

    def process_message(
        self,
        user_id: int,
        message: str,
        session_id: Optional[UUID] = None,
        event_id: Optional[int] = None
    ) -> ChatResult:
        """Process a user chat message.
        
        1. Get or create session
        2. Validate ownership and event access
        3. Build conversation context
        4. Process through NL2SQL pipeline
        5. Save messages and return result
        
        Args:
            user_id: Authenticated user ID
            message: User's message text
            session_id: Existing session UUID (optional)
            event_id: Event scope (optional)
            
        Returns:
            ChatResult with response and metadata
            
        Raises:
            SessionNotFoundError: If session_id provided but not found
            SessionAccessDeniedError: If user doesn't own the session
            EventAccessDeniedError: If user can't access the event
            QueryProcessingError: If NL2SQL processing fails
        """
        try:
            # Get or create session
            session, created = self._get_or_create_session(
                session_id, user_id, event_id
            )
            
            # Validate event access for event-scoped sessions
            if session.event_id:
                self._validate_event_access(user_id, session.event_id)
            
            # Save user message
            user_msg = self._session_manager.add_user_message(session, message)
            
            # Build context from previous messages
            context = self._context_builder.build_context(session.id)
            
            # Process through NL2SQL pipeline (with RAG enhancement)
            response_text, metadata = self._process_with_nl2sql(
                message, context, session.event_id, user_id=user_id
            )
            
            # Save assistant response
            assistant_msg = self._session_manager.add_assistant_message(
                session, response_text, metadata
            )
            
            # Commit transaction
            self._session_manager.commit()
            
            return ChatResult(
                response=response_text,
                session_id=session.id,
                message_id=assistant_msg.id,
                metadata=metadata or {},
                created_session=created
            )
            
        except (SessionNotFoundError, SessionAccessDeniedError, EventAccessDeniedError):
            self._session_manager.rollback()
            raise
        except QueryProcessingError:
            self._session_manager.rollback()
            raise
        except Exception as e:
            self._session_manager.rollback()
            logger.exception("Error processing chat message")
            raise QueryProcessingError(
                "An unexpected error occurred while processing your request",
                reason=str(e)
            ) from e

    def _get_or_create_session(
        self,
        session_id: Optional[UUID],
        user_id: int,
        event_id: Optional[int]
    ) -> tuple[ChatSession, bool]:
        """Get existing session or create new one.
        
        Args:
            session_id: Existing session UUID (optional)
            user_id: User ID
            event_id: Event scope (optional)
            
        Returns:
            Tuple of (session, created_flag)
            
        Raises:
            SessionNotFoundError: If session_id not found
            SessionAccessDeniedError: If user doesn't own session
        """
        if session_id:
            session = self._session_manager.get_session(session_id)
            if not session:
                raise SessionNotFoundError(f"Session {session_id} not found")
            
            if not self._session_manager.validate_session_ownership(session, user_id):
                raise SessionAccessDeniedError("Session belongs to another user")
            
            return session, False
        
        # Create new session
        session = self._session_manager.create_session(user_id, event_id)
        return session, True

    def _validate_event_access(self, user_id: int, event_id: int) -> None:
        """Validate user has access to the event.
        
        Args:
            user_id: User ID
            event_id: Event ID
            
        Raises:
            EventAccessDeniedError: If user can't access event
        """
        try:
            from indico.modules.events import Event
            from flask import session as flask_session
            
            event = Event.get(event_id)
            if not event:
                raise EventAccessDeniedError(event_id, "Event not found")
            
            user = flask_session.user
            if not event.can_access(user):
                raise EventAccessDeniedError(
                    event_id,
                    "You do not have access to this event"
                )
        except ImportError:
            # If Indico modules not available (testing), skip validation
            logger.warning("Indico event module not available, skipping access check")

    def _process_with_nl2sql(
        self,
        message: str,
        context: list[dict[str, str]],
        event_id: Optional[int],
        user_id: Optional[int] = None
    ) -> tuple[str, dict[str, Any]]:
        """Process message through NL2SQL pipeline with RAG enhancement.
        
        Args:
            message: User's message
            context: Conversation history
            event_id: Event scope (optional)
            user_id: User ID for permission filtering (optional)
            
        Returns:
            Tuple of (response_text, metadata)
        """
        # Initialize metadata
        metadata: dict[str, Any] = {}
        
        try:
            from indico_assistant.plugin import AssistantPlugin
            from indico_assistant.services.nl2sql import create_nl2sql_pipeline_from_plugin

            plugin = AssistantPlugin.instance
            if not plugin:
                raise ImportError("Assistant plugin instance not available")

            pipeline = create_nl2sql_pipeline_from_plugin(plugin)

            logger.debug(
                "Executing NL2SQL pipeline",
                extra={"event_id": event_id, "user_id": user_id}
            )

            result = pipeline.process(
                question=message,
                user_id=user_id or 0,
                event_ids=[event_id] if event_id else None,
                conversation_history=context,  # Feature 012: T006
            )

            response_text = result.answer or ""
            if not result.success:
                response_text = (
                    result.error.user_message
                    if result.error
                    else "Unable to process your query"
                )

            error_payload = None
            if result.error:
                error_payload = (
                    result.error.model_dump()
                    if hasattr(result.error, "model_dump")
                    else result.error.dict()
                )

            metadata.update({
                "sql_generated": result.generated_sql,
                "confidence": result.confidence,
                "data_sources": result.tables_accessed,
                "pipeline_success": result.success,
                "pipeline_error": error_payload,
            })

            return response_text, metadata

        except ImportError:
            # NL2SQL service not available, return mock response
            logger.warning("NL2SQL service not available, returning mock response")
            response = (
                f"I received your message: '{message}'. "
                "The NL2SQL pipeline is not configured."
            )
            
            metadata["mock_response"] = True
            return response, metadata
            
        except Exception as e:
            logger.exception("NL2SQL processing failed")
            raise QueryProcessingError(
                "Unable to process your query",
                reason=str(e)
            ) from e


# Default instance
_chat_service: ChatService | None = None


def get_chat_service() -> ChatService:
    """Get or create the default chat service instance.
    
    Returns:
        ChatService instance
    """
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
