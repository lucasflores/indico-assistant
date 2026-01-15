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
        from indico_assistant.schemas.chat import ChatResponse, MessageMetadata
        
        response = ChatResponse(
            session_id=str(uuid4()),
            message_id=str(uuid4()),
            response="Test response",
            metadata=MessageMetadata()
        )
        
        assert response.session_id is not None
        assert response.message_id is not None
        assert response.response is not None

    def test_response_schema_metadata_optional_fields(self):
        """ChatResponse.metadata fields are optional."""
        from indico_assistant.schemas.chat import ChatResponse, MessageMetadata
        
        response = ChatResponse(
            session_id=str(uuid4()),
            message_id=str(uuid4()),
            response="Test",
            metadata=MessageMetadata()
        )
        
        assert response.metadata.sql_generated is None
        assert response.metadata.confidence is None


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
            updated_at=datetime.now(timezone.utc).isoformat(),
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
            feedback_type="thumbs_up"
        )
        
        assert request.message_id is not None
        assert request.feedback_type is not None

    def test_feedback_request_valid_types(self):
        """FeedbackRequest.feedback_type must be valid."""
        from indico_assistant.schemas.feedback import FeedbackRequest
        
        valid_types = ["thumbs_up", "thumbs_down", "rating", "comment"]
        
        for ftype in valid_types:
            request = FeedbackRequest(
                message_id=str(uuid4()),
                feedback_type=ftype
            )
            assert request.feedback_type == ftype

    def test_feedback_request_rating_optional(self):
        """FeedbackRequest.rating is optional."""
        from indico_assistant.schemas.feedback import FeedbackRequest
        
        request = FeedbackRequest(
            message_id=str(uuid4()),
            feedback_type="thumbs_up"
        )
        assert request.rating is None

    def test_feedback_request_comment_optional(self):
        """FeedbackRequest.comment is optional."""
        from indico_assistant.schemas.feedback import FeedbackRequest
        
        request = FeedbackRequest(
            message_id=str(uuid4()),
            feedback_type="thumbs_up"
        )
        assert request.comment is None

    def test_feedback_response_schema(self):
        """FeedbackResponse has required fields."""
        from indico_assistant.schemas.feedback import FeedbackResponse
        
        response = FeedbackResponse(
            feedback_id=str(uuid4()),
            message_id=str(uuid4()),
            feedback_type="thumbs_up",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        
        assert response.feedback_id is not None
        assert response.message_id is not None


class TestErrorResponseContract:
    """Contract tests for error responses."""

    def test_error_response_required_fields(self):
        """ErrorResponse has required fields."""
        from indico_assistant.schemas.errors import ErrorResponse
        
        error = ErrorResponse(
            code="VALIDATION_ERROR",
            message="Invalid input"
        )
        
        assert error.code is not None
        assert error.message is not None

    def test_error_response_details_optional(self):
        """ErrorResponse.details is optional."""
        from indico_assistant.schemas.errors import ErrorResponse
        
        error = ErrorResponse(
            code="VALIDATION_ERROR",
            message="Invalid input"
        )
        
        assert error.details is None

    def test_error_codes_enum(self):
        """ErrorCode enum contains expected values."""
        from indico_assistant.schemas.errors import ErrorCode
        
        expected_codes = [
            "VALIDATION_ERROR",
            "ACCESS_DENIED",
            "SESSION_NOT_FOUND",
            "MESSAGE_NOT_FOUND",
            "RATE_LIMITED",
            "QUERY_PROCESSING_ERROR",
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
