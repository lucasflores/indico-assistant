"""Unit tests for session controllers.

Feature: 004-chat-api
Task: T029
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

import indico_assistant.controllers.sessions as sessions_module


class TestRHSessionList:
    """Tests for RHSessionList controller."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock authenticated user."""
        user = MagicMock()
        user.id = 123
        return user

    @pytest.fixture
    def controller(self, mock_user):
        """Create a session list controller instance."""
        from indico_assistant.controllers.sessions import RHSessionList
        
        ctrl = RHSessionList.__new__(RHSessionList)
        ctrl.user = mock_user
        return ctrl

    @pytest.fixture
    def mock_request(self):
        """Create and inject a mock request into the sessions module."""
        mock_req = MagicMock()
        original_request = getattr(sessions_module, 'request', None)
        sessions_module.request = mock_req
        yield mock_req
        if original_request:
            sessions_module.request = original_request

    def test_list_sessions_returns_paginated_results(self, controller, mock_request):
        """Test listing sessions with default pagination."""
        mock_sessions = [MagicMock() for _ in range(3)]
        for i, s in enumerate(mock_sessions):
            s.id = uuid4()
            s.event_id = None
            s.created_at = datetime.now(timezone.utc)
            s.last_message_at = datetime.now(timezone.utc)
            s.message_count = i + 1
        
        mock_request.args.get.side_effect = lambda k, d=None: {"limit": "20", "offset": "0"}.get(k, d)
        
        with patch('indico_assistant.controllers.sessions.get_session_manager') as mock_get:
            mock_manager = MagicMock()
            mock_get.return_value = mock_manager
            mock_manager.list_user_sessions.return_value = mock_sessions
            mock_manager.count_user_sessions.return_value = 3
            
            with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=199, retry_after=None
                )
                
                response, status = controller._process()
                
                assert status == 200
                data = response.get_json()
                assert len(data["sessions"]) == 3
                assert data["total"] == 3
                assert data["limit"] == 20
                assert data["offset"] == 0

    def test_list_sessions_respects_pagination_params(self, controller, mock_request):
        """Test custom pagination parameters."""
        mock_request.args.get.side_effect = lambda k, d=None: {"limit": "5", "offset": "10"}.get(k, d)
        
        with patch('indico_assistant.controllers.sessions.get_session_manager') as mock_get:
            mock_manager = MagicMock()
            mock_get.return_value = mock_manager
            mock_manager.list_user_sessions.return_value = []
            mock_manager.count_user_sessions.return_value = 50
            
            with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=199, retry_after=None
                )
                
                controller._process()
                
                mock_manager.list_user_sessions.assert_called_once_with(
                    user_id=123,
                    limit=5,
                    offset=10
                )

    def test_list_sessions_validates_limit_bounds(self, controller, mock_request):
        """Test limit must be within bounds."""
        mock_request.args.get.side_effect = lambda k, d=None: {"limit": "500", "offset": "0"}.get(k, d)
        
        with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
            from indico_assistant.services.chat.rate_limiter import RateLimitResult
            mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                allowed=True, remaining=199, retry_after=None
            )
            
            response, status = controller._process()
            
            assert status == 422
            data = response.get_json()
            assert data["error"] == "VALIDATION_ERROR"

    def test_list_sessions_validates_negative_offset(self, controller, mock_request):
        """Test offset must be non-negative."""
        mock_request.args.get.side_effect = lambda k, d=None: {"limit": "20", "offset": "-5"}.get(k, d)
        
        with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
            from indico_assistant.services.chat.rate_limiter import RateLimitResult
            mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                allowed=True, remaining=199, retry_after=None
            )
            
            response, status = controller._process()
            
            assert status == 422


class TestRHSessionDetail:
    """Tests for RHSessionDetail controller."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock authenticated user."""
        user = MagicMock()
        user.id = 123
        return user

    @pytest.fixture
    def controller(self, mock_user):
        """Create a session detail controller instance."""
        from indico_assistant.controllers.sessions import RHSessionDetail
        
        ctrl = RHSessionDetail.__new__(RHSessionDetail)
        ctrl.user = mock_user
        return ctrl

    def test_get_session_detail_returns_messages(self, controller):
        """Test retrieving session with messages."""
        session_id = uuid4()
        
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = 123
        mock_session.event_id = None
        mock_session.created_at = datetime.now(timezone.utc)
        mock_session.updated_at = datetime.now(timezone.utc)
        
        mock_messages = []
        for i, role in enumerate(["user", "assistant"]):
            msg = MagicMock()
            msg.id = uuid4()
            msg.role = role
            msg.content = f"Message {i}"
            msg.created_at = datetime.now(timezone.utc)
            msg.metadata = None
            mock_messages.append(msg)
        
        with patch('indico_assistant.controllers.sessions.get_session_manager') as mock_get:
            mock_manager = MagicMock()
            mock_get.return_value = mock_manager
            mock_manager.get_session.return_value = mock_session
            mock_manager.validate_session_ownership.return_value = True
            mock_manager.get_session_messages.return_value = mock_messages
            
            with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=199, retry_after=None
                )
                
                response, status = controller._process(str(session_id))
                
                assert status == 200
                data = response.get_json()
                assert data["session_id"] == str(session_id)
                assert len(data["messages"]) == 2

    def test_get_session_not_found(self, controller):
        """Test 404 when session doesn't exist."""
        session_id = uuid4()
        
        with patch('indico_assistant.controllers.sessions.get_session_manager') as mock_get:
            mock_manager = MagicMock()
            mock_get.return_value = mock_manager
            mock_manager.get_session.return_value = None
            
            with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=199, retry_after=None
                )
                
                response, status = controller._process(str(session_id))
                
                assert status == 404

    def test_get_session_access_denied(self, controller):
        """Test 403 when user doesn't own session."""
        session_id = uuid4()
        
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = 456  # Different user
        
        with patch('indico_assistant.controllers.sessions.get_session_manager') as mock_get:
            mock_manager = MagicMock()
            mock_get.return_value = mock_manager
            mock_manager.get_session.return_value = mock_session
            mock_manager.validate_session_ownership.return_value = False
            
            with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=199, retry_after=None
                )
                
                response, status = controller._process(str(session_id))
                
                assert status == 403

    def test_get_session_invalid_uuid(self, controller):
        """Test 422 for invalid UUID format."""
        with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
            from indico_assistant.services.chat.rate_limiter import RateLimitResult
            mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                allowed=True, remaining=199, retry_after=None
            )
            
            response, status = controller._process("not-a-uuid")
            
            assert status == 422


class TestRHSessionDelete:
    """Tests for RHSessionDelete controller."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock authenticated user."""
        user = MagicMock()
        user.id = 123
        return user

    @pytest.fixture
    def controller(self, mock_user):
        """Create a session delete controller instance."""
        from indico_assistant.controllers.sessions import RHSessionDelete
        
        ctrl = RHSessionDelete.__new__(RHSessionDelete)
        ctrl.user = mock_user
        return ctrl

    def test_delete_session_success(self, controller):
        """Test successful session deletion."""
        session_id = uuid4()
        
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = 123
        
        with patch('indico_assistant.controllers.sessions.get_session_manager') as mock_get:
            mock_manager = MagicMock()
            mock_get.return_value = mock_manager
            mock_manager.get_session.return_value = mock_session
            mock_manager.validate_session_ownership.return_value = True
            mock_manager.delete_session.return_value = True
            
            with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=59, retry_after=None
                )
                
                response, status = controller._process(str(session_id))
                
                assert status == 204
                mock_manager.commit.assert_called_once()

    def test_delete_session_not_found(self, controller):
        """Test 404 when session doesn't exist."""
        session_id = uuid4()
        
        with patch('indico_assistant.controllers.sessions.get_session_manager') as mock_get:
            mock_manager = MagicMock()
            mock_get.return_value = mock_manager
            mock_manager.get_session.return_value = None
            
            with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=59, retry_after=None
                )
                
                response, status = controller._process(str(session_id))
                
                assert status == 404

    def test_delete_session_access_denied(self, controller):
        """Test 403 when user doesn't own session."""
        session_id = uuid4()
        
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = 456
        
        with patch('indico_assistant.controllers.sessions.get_session_manager') as mock_get:
            mock_manager = MagicMock()
            mock_get.return_value = mock_manager
            mock_manager.get_session.return_value = mock_session
            mock_manager.validate_session_ownership.return_value = False
            
            with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=59, retry_after=None
                )
                
                response, status = controller._process(str(session_id))
                
                assert status == 403
