"""Integration tests for POST /chat endpoint.

Feature: 004-chat-api
Task: T021
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestChatEndpointIntegration:
    """Integration tests for the chat endpoint."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock authenticated user."""
        user = MagicMock()
        user.id = 123
        user.is_admin = False
        return user

    @pytest.fixture
    def mock_flask_session(self, mock_user):
        """Mock Flask session with authenticated user."""
        with patch('flask.session') as mock_session:
            mock_session.user = mock_user
            yield mock_session

    @pytest.fixture
    def chat_controller(self, mock_user):
        """Create a chat controller instance."""
        from indico_assistant.controllers.chat import RHChat
        
        controller = RHChat.__new__(RHChat)
        controller.user = mock_user
        return controller

    def test_process_returns_response_with_new_session(
        self, chat_controller, mock_user
    ):
        """Test chat returns response and creates new session."""
        session_id = uuid4()
        message_id = uuid4()
        
        with patch('indico_assistant.controllers.chat.request') as mock_request:
            mock_request.get_json.return_value = {
                "message": "What events are tomorrow?"
            }
            
            with patch('indico_assistant.controllers.chat.get_chat_service') as mock_get:
                from indico_assistant.services.chat.service import ChatResult
                
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                mock_service.process_message.return_value = ChatResult(
                    response="There are 3 events tomorrow.",
                    session_id=session_id,
                    message_id=message_id,
                    metadata={"sql_generated": "SELECT * FROM events"},
                    created_session=True
                )
                
                with patch('indico_assistant.controllers.chat.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status_code = chat_controller._process()
                    
                    assert status_code == 201  # Created
                    data = response.get_json()
                    assert data["session_id"] == str(session_id)
                    assert data["response"] == "There are 3 events tomorrow."

    def test_process_returns_response_with_existing_session(
        self, chat_controller, mock_user
    ):
        """Test chat uses existing session when session_id provided."""
        session_id = uuid4()
        message_id = uuid4()
        
        with patch('indico_assistant.controllers.chat.request') as mock_request:
            mock_request.get_json.return_value = {
                "message": "Show me the first one",
                "session_id": str(session_id)
            }
            
            with patch('indico_assistant.controllers.chat.get_chat_service') as mock_get:
                from indico_assistant.services.chat.service import ChatResult
                
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                mock_service.process_message.return_value = ChatResult(
                    response="The first event is Team Meeting.",
                    session_id=session_id,
                    message_id=message_id,
                    metadata={},
                    created_session=False
                )
                
                with patch('indico_assistant.controllers.chat.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=58, retry_after=None
                    )
                    
                    response, status_code = chat_controller._process()
                    
                    assert status_code == 200  # OK, not Created
                    mock_service.process_message.assert_called_once()
                    call_kwargs = mock_service.process_message.call_args[1]
                    assert call_kwargs['session_id'] == session_id

    def test_process_validates_message_required(self, chat_controller):
        """Test validation error when message is missing."""
        with patch('indico_assistant.controllers.chat.request') as mock_request:
            mock_request.get_json.return_value = {}
            
            with patch('indico_assistant.controllers.chat.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=59, retry_after=None
                )
                
                response, status_code = chat_controller._process()
                
                assert status_code == 422
                data = response.get_json()
                assert data["code"] == "VALIDATION_ERROR"

    def test_process_validates_message_not_empty(self, chat_controller):
        """Test validation error when message is empty string."""
        with patch('indico_assistant.controllers.chat.request') as mock_request:
            mock_request.get_json.return_value = {"message": ""}
            
            with patch('indico_assistant.controllers.chat.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=59, retry_after=None
                )
                
                response, status_code = chat_controller._process()
                
                assert status_code == 422

    def test_process_handles_session_not_found(self, chat_controller):
        """Test 404 error when session_id not found."""
        session_id = uuid4()
        
        with patch('indico_assistant.controllers.chat.request') as mock_request:
            mock_request.get_json.return_value = {
                "message": "Hello",
                "session_id": str(session_id)
            }
            
            with patch('indico_assistant.controllers.chat.get_chat_service') as mock_get:
                from indico_assistant.services.chat.service import SessionNotFoundError
                
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                mock_service.process_message.side_effect = SessionNotFoundError(
                    f"Session {session_id} not found"
                )
                
                with patch('indico_assistant.controllers.chat.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status_code = chat_controller._process()
                    
                    assert status_code == 404
                    data = response.get_json()
                    assert data["code"] == "SESSION_NOT_FOUND"

    def test_process_handles_session_access_denied(self, chat_controller):
        """Test 403 error when user doesn't own session."""
        session_id = uuid4()
        
        with patch('indico_assistant.controllers.chat.request') as mock_request:
            mock_request.get_json.return_value = {
                "message": "Hello",
                "session_id": str(session_id)
            }
            
            with patch('indico_assistant.controllers.chat.get_chat_service') as mock_get:
                from indico_assistant.services.chat.service import SessionAccessDeniedError
                
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                mock_service.process_message.side_effect = SessionAccessDeniedError(
                    "Session belongs to another user"
                )
                
                with patch('indico_assistant.controllers.chat.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status_code = chat_controller._process()
                    
                    assert status_code == 403
                    data = response.get_json()
                    assert data["code"] == "ACCESS_DENIED"

    def test_process_handles_event_access_denied(self, chat_controller):
        """Test 403 error when user can't access event."""
        with patch('indico_assistant.controllers.chat.request') as mock_request:
            mock_request.get_json.return_value = {
                "message": "What's in event 456?",
                "event_id": 456
            }
            
            with patch('indico_assistant.controllers.chat.get_chat_service') as mock_get:
                from indico_assistant.services.chat.service import EventAccessDeniedError
                
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                mock_service.process_message.side_effect = EventAccessDeniedError(
                    456, "Access denied to event"
                )
                
                with patch('indico_assistant.controllers.chat.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status_code = chat_controller._process()
                    
                    assert status_code == 403
                    data = response.get_json()
                    assert data["code"] == "ACCESS_DENIED"

    def test_process_handles_query_processing_error(self, chat_controller):
        """Test 500 error when query processing fails."""
        with patch('indico_assistant.controllers.chat.request') as mock_request:
            mock_request.get_json.return_value = {"message": "Complex query"}
            
            with patch('indico_assistant.controllers.chat.get_chat_service') as mock_get:
                from indico_assistant.services.chat.service import QueryProcessingError
                
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                mock_service.process_message.side_effect = QueryProcessingError(
                    "Failed to process query",
                    reason="LLM timeout"
                )
                
                with patch('indico_assistant.controllers.chat.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status_code = chat_controller._process()
                    
                    assert status_code == 500
                    data = response.get_json()
                    assert data["code"] == "QUERY_PROCESSING_ERROR"

    def test_process_returns_metadata_in_response(self, chat_controller):
        """Test response includes SQL and confidence metadata."""
        session_id = uuid4()
        message_id = uuid4()
        
        with patch('indico_assistant.controllers.chat.request') as mock_request:
            mock_request.get_json.return_value = {
                "message": "How many events are there?"
            }
            
            with patch('indico_assistant.controllers.chat.get_chat_service') as mock_get:
                from indico_assistant.services.chat.service import ChatResult
                
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                mock_service.process_message.return_value = ChatResult(
                    response="There are 42 events.",
                    session_id=session_id,
                    message_id=message_id,
                    metadata={
                        "sql_generated": "SELECT COUNT(*) FROM events",
                        "confidence": 0.95,
                        "data_sources": ["events"]
                    },
                    created_session=True
                )
                
                with patch('indico_assistant.controllers.chat.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status_code = chat_controller._process()
                    
                    data = response.get_json()
                    assert "metadata" in data
                    assert data["metadata"]["sql_generated"] == "SELECT COUNT(*) FROM events"
                    assert data["metadata"]["confidence"] == 0.95

    def test_process_accepts_event_scoped_request(self, chat_controller):
        """Test chat request with event_id scope."""
        session_id = uuid4()
        message_id = uuid4()
        
        with patch('indico_assistant.controllers.chat.request') as mock_request:
            mock_request.get_json.return_value = {
                "message": "What sessions are in this event?",
                "event_id": 789
            }
            
            with patch('indico_assistant.controllers.chat.get_chat_service') as mock_get:
                from indico_assistant.services.chat.service import ChatResult
                
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                mock_service.process_message.return_value = ChatResult(
                    response="This event has 5 sessions.",
                    session_id=session_id,
                    message_id=message_id,
                    metadata={},
                    created_session=True
                )
                
                with patch('indico_assistant.controllers.chat.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status_code = chat_controller._process()
                    
                    assert status_code == 201
                    mock_service.process_message.assert_called_once()
                    call_kwargs = mock_service.process_message.call_args[1]
                    assert call_kwargs['event_id'] == 789
