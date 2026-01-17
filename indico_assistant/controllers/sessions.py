"""Session management endpoint controllers.

Handles session listing, detail view, and deletion.

Feature: 004-chat-api
Tasks: T023, T024, T025
"""

from __future__ import annotations

import logging
from uuid import UUID

from flask import jsonify, request

from indico_assistant.controllers.base import RHChatBase
from indico_assistant.schemas.session import (
    MessageItem,
    SessionDetailResponse,
    SessionListItem,
    SessionListResponse,
)
from indico_assistant.services.chat import (
    SessionAccessDeniedError,
    SessionNotFoundError,
    get_session_manager,
)
from indico_assistant.services.chat.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


class RHSessionList(RHChatBase):
    """Request handler for GET /sessions endpoint.
    
    Lists all chat sessions for the authenticated user with pagination.
    """

    def _check_access(self) -> None:
        """Verify user authentication and rate limits."""
        super()._check_access()
        
        # Check rate limit for read requests
        rate_limiter = get_rate_limiter()
        rate_result = rate_limiter.check_rate(self.user.id, "read")
        
        if not rate_result.allowed:
            raise self._rate_limit_error(rate_result.retry_after)

    def _process(self):
        """List user's chat sessions.
        
        Query Parameters:
            limit: Max items per page (default 20, max 100)
            offset: Items to skip (default 0)
            
        Returns:
            JSON response with paginated session list
        """
        # Parse pagination parameters
        try:
            limit = int(request.args.get("limit", 20))
            offset = int(request.args.get("offset", 0))
        except ValueError:
            return self._error_response(
                "VALIDATION_ERROR",
                "Invalid pagination parameters",
                status=422
            )
        
        # Validate pagination bounds
        if limit < 1 or limit > 100:
            return self._error_response(
                "VALIDATION_ERROR",
                "Limit must be between 1 and 100",
                status=422
            )
        
        if offset < 0:
            return self._error_response(
                "VALIDATION_ERROR",
                "Offset must be non-negative",
                status=422
            )
        
        try:
            session_manager = get_session_manager()
            
            # Get user's sessions
            sessions = session_manager.list_user_sessions(
                user_id=self.user.id,
                limit=limit,
                offset=offset
            )
            
            # Get total count for pagination
            total = session_manager.count_user_sessions(self.user.id)
            
            # Build response items
            items = []
            for session in sessions:
                items.append(SessionListItem(
                    session_id=str(session.id),
                    event_id=session.event_id,
                    created_at=session.created_at.isoformat(),
                    last_message_at=session.last_message_at.isoformat() if session.last_message_at else session.updated_at.isoformat(),
                    message_count=session.message_count
                ))
            
            response = SessionListResponse(
                sessions=items,
                total=total,
                limit=limit,
                offset=offset
            )
            
            return jsonify(response.model_dump(mode='json')), 200
            
        except Exception as e:
            logger.exception("Error listing sessions")
            return self._error_response(
                "INTERNAL_ERROR",
                "Failed to retrieve sessions",
                status=500
            )


class RHSessionDetail(RHChatBase):
    """Request handler for GET /sessions/<id> endpoint.
    
    Retrieves a specific session with its message history.
    """

    def _check_access(self) -> None:
        """Verify user authentication and rate limits."""
        super()._check_access()
        
        # Check rate limit for read requests
        rate_limiter = get_rate_limiter()
        rate_result = rate_limiter.check_rate(self.user.id, "read")
        
        if not rate_result.allowed:
            raise self._rate_limit_error(rate_result.retry_after)

    def _process(self, session_id: str):
        """Get session details with message history.
        
        Args:
            session_id: UUID of the session to retrieve
            
        Returns:
            JSON response with session details and messages
        """
        # Parse session_id
        try:
            uuid_id = UUID(session_id)
        except ValueError:
            return self._error_response(
                "VALIDATION_ERROR",
                "Invalid session_id format",
                status=422
            )
        
        try:
            session_manager = get_session_manager()
            
            # Get session
            session = session_manager.get_session(uuid_id)
            if not session:
                return self._error_response(
                    "SESSION_NOT_FOUND",
                    "Session not found",
                    status=404
                )
            
            # Validate ownership
            if not session_manager.validate_session_ownership(session, self.user.id):
                return self._error_response(
                    "ACCESS_DENIED",
                    "Session belongs to another user",
                    status=403
                )
            
            # Get messages
            messages = session_manager.get_session_messages(uuid_id)
            
            # Build message items
            message_items = []
            for msg in messages:
                message_items.append(MessageItem(
                    message_id=str(msg.id),
                    role=msg.role,
                    content=msg.content,
                    created_at=msg.created_at.isoformat(),
                    metadata=msg.metadata
                ))
            
            response = SessionDetailResponse(
                session_id=str(session.id),
                event_id=session.event_id,
                created_at=session.created_at.isoformat(),
                updated_at=session.updated_at.isoformat(),
                messages=message_items
            )
            
            return jsonify(response.model_dump(exclude_none=True, mode='json')), 200
            
        except Exception as e:
            logger.exception("Error retrieving session")
            return self._error_response(
                "INTERNAL_ERROR",
                "Failed to retrieve session",
                status=500
            )


class RHSessionDelete(RHChatBase):
    """Request handler for DELETE /sessions/<id> endpoint.
    
    Deletes a chat session and all its messages.
    """

    def _check_access(self) -> None:
        """Verify user authentication and rate limits."""
        super()._check_access()
        
        # Check rate limit for chat requests (delete is a write operation)
        rate_limiter = get_rate_limiter()
        rate_result = rate_limiter.check_rate(self.user.id, "chat")
        
        if not rate_result.allowed:
            raise self._rate_limit_error(rate_result.retry_after)

    def _process(self, session_id: str):
        """Delete a chat session.
        
        Args:
            session_id: UUID of the session to delete
            
        Returns:
            204 No Content on success
        """
        # Parse session_id
        try:
            uuid_id = UUID(session_id)
        except ValueError:
            return self._error_response(
                "VALIDATION_ERROR",
                "Invalid session_id format",
                status=422
            )
        
        try:
            session_manager = get_session_manager()
            
            # Get session to validate ownership
            session = session_manager.get_session(uuid_id)
            if not session:
                return self._error_response(
                    "SESSION_NOT_FOUND",
                    "Session not found",
                    status=404
                )
            
            # Validate ownership
            if not session_manager.validate_session_ownership(session, self.user.id):
                return self._error_response(
                    "ACCESS_DENIED",
                    "Session belongs to another user",
                    status=403
                )
            
            # Delete session (cascade will delete messages and feedback)
            deleted = session_manager.delete_session(uuid_id)
            session_manager.commit()
            
            if deleted:
                return "", 204
            else:
                return self._error_response(
                    "SESSION_NOT_FOUND",
                    "Session not found",
                    status=404
                )
                
        except Exception as e:
            session_manager.rollback()
            logger.exception("Error deleting session")
            return self._error_response(
                "INTERNAL_ERROR",
                "Failed to delete session",
                status=500
            )
