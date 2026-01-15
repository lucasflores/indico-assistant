"""Chat endpoint controller.

Handles POST /chat requests for conversational queries.

Feature: 004-chat-api
Task: T017
"""

from __future__ import annotations

import logging
from uuid import UUID

from flask import jsonify, request
from pydantic import ValidationError

from indico_assistant.controllers.base import RHChatBase
from indico_assistant.schemas.chat import ChatRequest, ChatResponse, MessageMetadata
from indico_assistant.services.chat import (
    ChatServiceError,
    EventAccessDeniedError,
    QueryProcessingError,
    SessionAccessDeniedError,
    SessionNotFoundError,
    get_chat_service,
)
from indico_assistant.services.chat.rate_limiter import (
    get_rate_limiter,
)

logger = logging.getLogger(__name__)


class RHChat(RHChatBase):
    """Request handler for POST /chat endpoint.
    
    Processes user messages through the NL2SQL pipeline
    with session management and conversation context.
    """

    def _check_access(self) -> None:
        """Verify user authentication and rate limits."""
        super()._check_access()
        
        # Check rate limit for chat requests
        rate_limiter = get_rate_limiter()
        rate_result = rate_limiter.check_rate(self.user.id, "chat")
        
        if not rate_result.allowed:
            from indico_assistant.schemas.errors import ErrorCode
            raise self._rate_limit_error(rate_result.retry_after)

    def _process(self):
        """Process the chat request.
        
        Returns:
            JSON response with assistant message and metadata
        """
        # Parse and validate request
        try:
            data = request.get_json()
            if not data:
                return self._error_response(
                    "VALIDATION_ERROR",
                    "Request body is required",
                    422
                )
            
            chat_request = ChatRequest.model_validate(data)
        except ValidationError as e:
            return self._validation_error(e)
        except Exception as e:
            logger.warning("Failed to parse request body: %s", e)
            return self._error_response(
                "VALIDATION_ERROR",
                "Invalid request body",
                422
            )

        # Parse session_id if provided
        session_id = None
        if chat_request.session_id:
            try:
                session_id = UUID(chat_request.session_id)
            except ValueError:
                return self._error_response(
                    "VALIDATION_ERROR",
                    "Invalid session_id format",
                    422
                )

        # Process the message
        try:
            chat_service = get_chat_service()
            result = chat_service.process_message(
                user_id=self.user.id,
                message=chat_request.message,
                session_id=session_id,
                event_id=chat_request.event_id
            )
            
            # Build response
            response = ChatResponse(
                session_id=str(result.session_id),
                message_id=str(result.message_id),
                response=result.response,
                metadata=MessageMetadata(
                    sql_generated=result.metadata.get("sql_generated"),
                    confidence=result.metadata.get("confidence"),
                    data_sources=result.metadata.get("data_sources", [])
                )
            )
            
            status_code = 201 if result.created_session else 200
            return jsonify(response.model_dump(exclude_none=True)), status_code
            
        except SessionNotFoundError:
            return self._error_response(
                "SESSION_NOT_FOUND",
                "Session not found",
                404
            )
        except SessionAccessDeniedError:
            return self._error_response(
                "ACCESS_DENIED",
                "Session belongs to another user",
                403
            )
        except EventAccessDeniedError as e:
            return self._error_response(
                "ACCESS_DENIED",
                f"Access denied to event {e.event_id}",
                403
            )
        except QueryProcessingError as e:
            logger.exception("Query processing failed")
            return self._error_response(
                "QUERY_PROCESSING_ERROR",
                "Failed to process query",
                500,
                details=e.reason
            )
        except ChatServiceError as e:
            logger.exception("Chat service error")
            return self._error_response(
                "INTERNAL_ERROR",
                "An unexpected error occurred",
                500
            )
        except Exception as e:
            logger.exception("Unexpected error in chat endpoint")
            return self._error_response(
                "INTERNAL_ERROR",
                "An unexpected error occurred",
                500
            )
