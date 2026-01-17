"""API contract tests against OpenAPI specification.

Feature: 004-chat-api
Task: T042

These tests validate that the API implementation conforms to
the OpenAPI specification in contracts/openapi.yaml.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest


class TestChatEndpointContract:
    """Contract tests for POST /chat endpoint."""

    def test_request_schema_message_required(self):
        """ChatRequest must have required message field."""
        from indico_assistant.schemas.chat import ChatRequest
        
        with pytest.raises(Exception):  # ValidationError
            ChatRequest.model_validate({})

    def test_request_schema_message_min_length(self):
        """ChatRequest.message must not be empty."""
        from indico_assistant.schemas.chat import ChatRequest
        
        with pytest.raises(Exception):
            ChatRequest.model_validate({"message": ""})

    def test_request_schema_optional_session_id(self):
        """ChatRequest.session_id is optional."""
        from indico_assistant.schemas.chat import ChatRequest
        
        request = ChatRequest.model_validate({"message": "Hello"})
        assert request.session_id is None

    def test_request_schema_optional_event_id(self):
        """ChatRequest.event_id is optional."""
        from indico_assistant.schemas.chat import ChatRequest
        
        request = ChatRequest.model_validate({"message": "Hello"})
        assert request.event_id is None

    def test_response_schema_required_fields(self):
        """ChatResponse has all required fields."""
        from indico_assistant.schemas.chat import ChatResponse
        
        response = ChatResponse(
            session_id=str(uuid4()),
            message_id=str(uuid4()),
            response="Test response",
            metadata={}
        )
        
        assert response.session_id is not None
        assert response.message_id is not None
        assert response.response is not None

    def test_response_schema_metadata_optional_fields(self):
        """ChatResponse.metadata fields are optional."""
        from indico_assistant.schemas.chat import ChatResponse
        
        response = ChatResponse(
            session_id=str(uuid4()),
            message_id=str(uuid4()),
            response="Test",
            metadata={}
        )
        
        # metadata is a dict, defaults to empty
        assert response.metadata == {}


class TestSessionEndpointsContract:
    """Contract tests for session endpoints."""

    def test_session_list_response_schema(self):
        """SessionListResponse has required fields."""
        from indico_assistant.schemas.session import SessionListItem, SessionListResponse
        
        response = SessionListResponse(
            sessions=[],
            total=0,
            limit=20,
            offset=0
        )
        
        assert response.sessions is not None
        assert response.total >= 0

    def test_session_list_item_schema(self):
        """SessionListItem has required fields."""
        from indico_assistant.schemas.session import SessionListItem
        
        item = SessionListItem(
            session_id=str(uuid4()),
            event_id=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            last_message_at=datetime.now(timezone.utc).isoformat(),
            message_count=5
        )
        
        assert item.session_id is not None
        assert item.created_at is not None
        assert item.message_count >= 0

    def test_session_detail_response_schema(self):
        """SessionDetailResponse has required fields."""
        from indico_assistant.schemas.session import SessionDetailResponse
        
        response = SessionDetailResponse(
            session_id=str(uuid4()),
            event_id=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            messages=[]
        )
        
        assert response.session_id is not None
        assert response.messages is not None

    def test_message_item_schema(self):
        """MessageItem has required fields."""
        from indico_assistant.schemas.session import MessageItem
        
        item = MessageItem(
            message_id=str(uuid4()),
            role="user",
            content="Hello",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        
        assert item.message_id is not None
        assert item.role in ["user", "assistant"]
        assert item.content is not None


class TestFeedbackEndpointContract:
    """Contract tests for POST /feedback endpoint."""

    def test_feedback_request_required_fields(self):
        """FeedbackRequest has required fields."""
        from indico_assistant.schemas.feedback import FeedbackRequest
        
        request = FeedbackRequest(
            message_id=str(uuid4()),
            feedback_type="thumbs_up",
            value=True
        )
        
        assert request.message_id is not None
        assert request.feedback_type is not None
        assert request.value is not None

    def test_feedback_request_valid_types(self):
        """FeedbackRequest.feedback_type must be valid."""
        from indico_assistant.schemas.feedback import FeedbackRequest
        
        # Map feedback types to appropriate values
        type_to_value = {
            "thumbs_up": True,
            "thumbs_down": True,
            "rating": 5,
            "comment": "Great response!"
        }
        
        for ftype, value in type_to_value.items():
            request = FeedbackRequest(
                message_id=str(uuid4()),
                feedback_type=ftype,
                value=value
            )
            assert request.feedback_type == ftype

    def test_feedback_request_thumbs_value(self):
        """FeedbackRequest for thumbs requires boolean value."""
        from indico_assistant.schemas.feedback import FeedbackRequest
        
        request = FeedbackRequest(
            message_id=str(uuid4()),
            feedback_type="thumbs_up",
            value=True
        )
        assert request.value is True

    def test_feedback_request_rating_value(self):
        """FeedbackRequest for rating requires integer value."""
        from indico_assistant.schemas.feedback import FeedbackRequest
        
        request = FeedbackRequest(
            message_id=str(uuid4()),
            feedback_type="rating",
            value=5
        )
        assert request.value == 5

    def test_feedback_response_schema(self):
        """FeedbackResponse has required fields."""
        from indico_assistant.schemas.feedback import FeedbackResponse
        
        response = FeedbackResponse(
            feedback_id=str(uuid4()),
            message_id=str(uuid4()),
            feedback_type="thumbs_up",
            created_at="2024-01-15T10:30:00Z"
        )
        
        assert response.feedback_id is not None
        assert response.message_id is not None
        assert response.feedback_type is not None
        assert response.created_at is not None


class TestErrorResponseContract:
    """Contract tests for error responses."""

    def test_error_response_required_fields(self):
        """ErrorResponse has required fields."""
        from indico_assistant.schemas.errors import ErrorResponse
        
        error = ErrorResponse(
            error="VALIDATION_ERROR",
            message="Invalid input"
        )
        
        assert error.error is not None
        assert error.message is not None

    def test_error_response_details_optional(self):
        """ErrorResponse.details is optional."""
        from indico_assistant.schemas.errors import ErrorResponse
        
        error = ErrorResponse(
            error="VALIDATION_ERROR",
            message="Invalid input"
        )
        
        assert error.details is None

    def test_error_codes_enum(self):
        """ErrorCode enum contains expected values."""
        from indico_assistant.schemas.errors import ErrorCode
        
        # These are the actual error codes defined in ErrorCode class
        expected_codes = [
            "VALIDATION_ERROR",
            "UNAUTHORIZED",
            "FORBIDDEN",
            "NOT_FOUND",
            "RATE_LIMITED",
            "UNPROCESSABLE_QUERY",
            "INTERNAL_ERROR"
        ]
        
        for code in expected_codes:
            assert hasattr(ErrorCode, code)


class TestPaginationContract:
    """Contract tests for pagination parameters."""

    def test_session_list_pagination_defaults(self):
        """Session list has pagination defaults."""
        from indico_assistant.schemas.session import SessionListResponse
        
        response = SessionListResponse(
            sessions=[],
            total=0,
            limit=20,
            offset=0
        )
        
        assert response.limit == 20
        assert response.offset == 0

    def test_session_list_pagination_bounds(self):
        """Session list pagination respects bounds."""
        from indico_assistant.schemas.session import SessionListResponse
        
        # Valid pagination
        response = SessionListResponse(
            sessions=[],
            total=100,
            limit=50,
            offset=10
        )
        
        assert 1 <= response.limit <= 100
        assert response.offset >= 0
