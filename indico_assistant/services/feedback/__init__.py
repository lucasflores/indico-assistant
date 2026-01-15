"""Feedback service package for indico_assistant.

Provides services for collecting and managing user feedback
on assistant responses.

Feature: 004-chat-api
Task: T032
"""

from indico_assistant.services.feedback.service import (
    FeedbackService,
    FeedbackServiceError,
    MessageAccessDeniedError,
    MessageNotFoundError,
    get_feedback_service,
)

__all__ = [
    "FeedbackService",
    "FeedbackServiceError",
    "MessageAccessDeniedError",
    "MessageNotFoundError",
    "get_feedback_service",
]
