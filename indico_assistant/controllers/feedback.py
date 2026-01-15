"""Feedback endpoint controller.

Handles POST /feedback requests for collecting user feedback.

Feature: 004-chat-api
Task: T033
"""

from __future__ import annotations

import logging
from uuid import UUID

from flask import jsonify, request
from pydantic import ValidationError

from indico_assistant.controllers.base import RHChatBase
from indico_assistant.schemas.feedback import FeedbackRequest, FeedbackResponse
from indico_assistant.services.chat.rate_limiter import get_rate_limiter
from indico_assistant.services.feedback import (
    MessageAccessDeniedError,
    MessageNotFoundError,
    get_feedback_service,
)

logger = logging.getLogger(__name__)


class RHFeedback(RHChatBase):
    """Request handler for POST /feedback endpoint.
    
    Collects user feedback on assistant responses.
    Supports thumbs up/down, ratings, and comments.
    """

    def _check_access(self) -> None:
        """Verify user authentication and rate limits."""
        super()._check_access()
        
        # Check rate limit for chat requests (feedback is a write operation)
        rate_limiter = get_rate_limiter()
        rate_result = rate_limiter.check_rate(self.user.id, "chat")
        
        if not rate_result.allowed:
            raise self._rate_limit_error(rate_result.retry_after)

    def _process(self):
        """Process the feedback submission.
        
        Returns:
            JSON response with feedback confirmation
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
            
            feedback_request = FeedbackRequest.model_validate(data)
        except ValidationError as e:
            return self._validation_error(e)
        except Exception as e:
            logger.warning("Failed to parse request body: %s", e)
            return self._error_response(
                "VALIDATION_ERROR",
                "Invalid request body",
                422
            )

        # Parse message_id
        try:
            message_id = UUID(feedback_request.message_id)
        except ValueError:
            return self._error_response(
                "VALIDATION_ERROR",
                "Invalid message_id format",
                422
            )

        # Submit feedback
        try:
            feedback_service = get_feedback_service()
            feedback = feedback_service.submit_feedback(
                user_id=self.user.id,
                message_id=message_id,
                feedback_type=feedback_request.feedback_type,
                rating=feedback_request.rating,
                comment=feedback_request.comment
            )
            feedback_service.commit()
            
            response = FeedbackResponse(
                feedback_id=str(feedback.id),
                message_id=str(feedback.message_id),
                feedback_type=feedback.feedback_type,
                created_at=feedback.created_at.isoformat()
            )
            
            return jsonify(response.model_dump()), 201
            
        except MessageNotFoundError:
            return self._error_response(
                "MESSAGE_NOT_FOUND",
                "Message not found",
                404
            )
        except MessageAccessDeniedError:
            return self._error_response(
                "ACCESS_DENIED",
                "Cannot provide feedback on messages from other users' sessions",
                403
            )
        except Exception as e:
            feedback_service.rollback()
            logger.exception("Error submitting feedback")
            return self._error_response(
                "INTERNAL_ERROR",
                "Failed to submit feedback",
                500
            )
