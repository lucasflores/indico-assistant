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

    RATE_LIMIT = "read"  # a vote spends no LLM money (spec 020)

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
                    status=422
                )
            
            feedback_request = FeedbackRequest.model_validate(data)
        except ValidationError as e:
            return self._validation_error(str(e))
        except Exception as e:
            logger.warning("Failed to parse request body: %s", e)
            return self._error_response(
                "VALIDATION_ERROR",
                "Invalid request body",
                status=422
            )

        # message_id is already parsed as UUID by the schema
        message_id = feedback_request.message_id

        # Extract rating/comment from value based on feedback_type
        rating = None
        comment = None
        if feedback_request.feedback_type == 'rating':
            rating = feedback_request.value
        elif feedback_request.feedback_type == 'comment':
            comment = feedback_request.value

        # Submit feedback
        try:
            feedback_service = get_feedback_service()
            feedback = feedback_service.submit_feedback(
                user_id=self.user.id,
                message_id=message_id,
                feedback_type=feedback_request.feedback_type,
                rating=rating,
                comment=comment,
                thumb_comment=feedback_request.comment,
            )
            feedback_service.commit()
            
            response = FeedbackResponse(
                feedback_id=str(feedback.id),
                message_id=str(feedback.message_id),
                feedback_type=feedback.feedback_type,
                created_at=feedback.created_at.isoformat()
            )
            
            return jsonify(response.model_dump(mode='json')), 201
            
        except MessageNotFoundError:
            return self._error_response(
                "MESSAGE_NOT_FOUND",
                "Message not found",
                status=404
            )
        except MessageAccessDeniedError:
            return self._error_response(
                "ACCESS_DENIED",
                "Cannot provide feedback on messages from other users' sessions",
                status=403
            )
        except Exception as e:
            feedback_service.rollback()
            logger.exception("Error submitting feedback")
            return self._error_response(
                "INTERNAL_ERROR",
                "Failed to submit feedback",
                status=500
            )


class RHFeedbackDelete(RHChatBase):
    """DELETE /feedback/<id>: take back a thumbs vote and its comment (spec 020 T046). 204; 404 when the user has
    no such vote, someone else's included."""

    RATE_LIMIT = "read"

    def _process(self):
        try:
            feedback_id = UUID(request.view_args["feedback_id"])
        except ValueError:
            return self._error_response("VALIDATION_ERROR", "Invalid feedback_id format", status=422)
        feedback_service = get_feedback_service()
        if not feedback_service.withdraw_feedback(self.user.id, feedback_id):
            return self._error_response("FEEDBACK_NOT_FOUND", "Feedback not found", status=404)
        feedback_service.commit()
        return "", 204
