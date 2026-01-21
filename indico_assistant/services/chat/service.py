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
from indico_assistant.services.chat.citations import (
    CitationBuilder,
    SourceCitation,
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

    def _get_base_url(self) -> str:
        """Get base URL for citation links from Indico config.
        
        Feature: 015-chat-source-citations
        Task: T012
        
        Returns:
            Base URL from Indico config (e.g., 'http://127.0.0.1:8000')
        """
        try:
            # Get from Indico's config (the actual instance URL)
            from indico.core.config import config
            if hasattr(config, 'BASE_URL') and config.BASE_URL:
                return config.BASE_URL.rstrip('/')
        except (ImportError, AttributeError):
            pass
        
        try:
            # Fallback to plugin setting if configured
            from indico_assistant.plugin import AssistantPlugin
            plugin = AssistantPlugin.instance
            if plugin and hasattr(plugin, 'settings'):
                base_url = plugin.settings.get('base_url')
                if base_url:
                    return base_url.rstrip('/')
        except (ImportError, AttributeError, RuntimeError):
            pass
        
        return 'http://localhost:8000'

    def _generate_event_citations(self, event_ids: list[int]) -> list[str]:
        """Generate markdown citation links for event IDs.
        
        Feature: 015-chat-source-citations
        Task: T014
        
        Args:
            event_ids: List of event IDs to cite
            
        Returns:
            List of markdown citation links
        """
        if not event_ids:
            return []
        
        base_url = self._get_base_url()
        builder = CitationBuilder(base_url=base_url)
        
        citations = []
        for event_id in event_ids:
            citation = builder.build_event_citation(event_id)
            citations.append(citation)
        
        return citations

    def _extract_document_citations(self, search_results: list) -> list[dict]:
        """Extract document citation metadata from RAG search results.
        
        Feature: 015-chat-source-citations
        Task: T023
        
        Args:
            search_results: List of SearchResult objects from vector search
            
        Returns:
            List of citation metadata dicts with type, IDs, URL, description
        """
        if not search_results:
            return []
        
        base_url = self._get_base_url()
        builder = CitationBuilder(base_url=base_url)
        
        citations = []
        seen_files = set()  # Dedup by file_id
        
        for result in search_results:
            # Extract metadata (Feature 011: T004 ensures these are present)
            metadata = getattr(result, 'metadata', {}) or {}
            contribution_id = metadata.get('contribution_id')
            file_id = metadata.get('file_id')
            filename = metadata.get('filename', 'document')
            
            # Skip if missing required IDs or already seen
            if not contribution_id or not file_id or file_id in seen_files:
                continue
            
            seen_files.add(file_id)
            
            # Extract event_id and attachment_id
            event_id = getattr(result, 'event_id', None)
            attachment_id = metadata.get('attachment_id')
            
            # Skip if missing core identifiers
            if not event_id or not attachment_id:
                continue
            
            # Build citation URL
            citation_url = builder.build_document_url(
                event_id=event_id,
                contribution_id=contribution_id,
                attachment_id=attachment_id,
                file_id=file_id,
                filename=filename
            )
            
            citations.append({
                "type": "document",
                "event_id": event_id,
                "contribution_id": contribution_id,
                "attachment_id": attachment_id,
                "file_id": file_id,
                "filename": filename,
                "url": citation_url,
                "description": f"Document: {filename}"  # Feature 015: T030 - type-specific prefix
            })
        
        return citations

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

            # Feature 015: Extract event IDs and generate citations (T013, T014)
            source_event_ids = getattr(result, 'source_event_ids', [])
            data_sources = []
            
            # Build citation metadata for event sources
            if source_event_ids:
                base_url = self._get_base_url()
                builder = CitationBuilder(base_url=base_url)
                
                for event_id in source_event_ids:
                    citation_url = builder.build_event_url(event_id)
                    data_sources.append({
                        "type": "event",
                        "event_id": event_id,
                        "url": citation_url,
                        "description": f"Event: {event_id}"  # Feature 015: T030 - type-specific prefix
                    })
            
            # Legacy fallback: include table names if no event sources
            if not data_sources and result.tables_accessed:
                data_sources = result.tables_accessed
            
            metadata.update({
                "sql_generated": result.generated_sql,
                "confidence": result.confidence,
                "data_sources": data_sources,  # Feature 015: New dict format
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
