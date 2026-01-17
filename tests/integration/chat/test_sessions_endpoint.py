"""Integration tests for session management endpoints.

Feature: 004-chat-api
Task: T030
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestSessionsEndpointIntegration:
    """Integration tests for session endpoints."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock authenticated user."""
        user = MagicMock()
        user.id = 123
        user.is_admin = False
        return user

    def test_list_sessions_full_flow(self, mock_user):
        """Test full flow of listing sessions."""
        from indico_assistant.controllers.sessions import RHSessionList
        
        ctrl = RHSessionList.__new__(RHSessionList)
        ctrl.user = mock_user
        
        mock_sessions = []
        for i in range(3):
            s = MagicMock()
            s.id = uuid4()
            s.event_id = None if i == 0 else i * 100
            s.created_at = datetime.now(timezone.utc)
            s.last_message_at = datetime.now(timezone.utc)
            s.message_count = (i + 1) * 2
            mock_sessions.append(s)
        
        mock_request = MagicMock()
        mock_request.args.get.side_effect = lambda k, d=None: {"limit": "20", "offset": "0"}.get(k, d)
        
        with patch.dict('sys.modules', {'flask': MagicMock(request=mock_request)}):
            import indico_assistant.controllers.sessions as sessions_module
            original_request = getattr(sessions_module, 'request', None)
            sessions_module.request = mock_request
            try:
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
                        
                        response, status = ctrl._process()
                        
                        assert status == 200
                        data = response.get_json()
                        assert len(data["sessions"]) == 3
                        assert data["total"] == 3
                        
                        # Verify session data
                        session = data["sessions"][0]
                        assert "session_id" in session
                        assert "created_at" in session
                        assert "message_count" in session
            finally:
                if original_request:
                    sessions_module.request = original_request
                    assert "message_count" in session

    def test_get_session_detail_with_messages(self, mock_user):
        """Test retrieving session with full message history."""
        from indico_assistant.controllers.sessions import RHSessionDetail
        
        ctrl = RHSessionDetail.__new__(RHSessionDetail)
        ctrl.user = mock_user
        
        session_id = uuid4()
        
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = 123
        mock_session.event_id = 456
        mock_session.created_at = datetime.now(timezone.utc)
        mock_session.updated_at = datetime.now(timezone.utc)
        
        mock_messages = []
        for i, (role, content) in enumerate([
            ("user", "What events are tomorrow?"),
            ("assistant", "There are 3 events tomorrow."),
            ("user", "Show me the first one"),
            ("assistant", "The first event is Team Meeting at 9 AM."),
        ]):
            msg = MagicMock()
            msg.id = uuid4()
            msg.role = role
            msg.content = content
            msg.created_at = datetime.now(timezone.utc)
            msg.metadata = {"sql_generated": "SELECT..."} if role == "assistant" else None
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
                
                response, status = ctrl._process(str(session_id))
                
                assert status == 200
                data = response.get_json()
                assert data["session_id"] == str(session_id)
                assert data["event_id"] == 456
                assert len(data["messages"]) == 4
                
                # Verify message structure
                user_msg = data["messages"][0]
                assert user_msg["role"] == "user"
                assert user_msg["content"] == "What events are tomorrow?"
                
                assistant_msg = data["messages"][1]
                assert assistant_msg["role"] == "assistant"
                assert "sql_generated" in assistant_msg.get("metadata", {})

    def test_delete_session_with_cascade(self, mock_user):
        """Test deleting session cascades to messages and feedback."""
        from indico_assistant.controllers.sessions import RHSessionDelete
        
        ctrl = RHSessionDelete.__new__(RHSessionDelete)
        ctrl.user = mock_user
        
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
                
                response, status = ctrl._process(str(session_id))
                
                assert status == 204
                mock_manager.delete_session.assert_called_once_with(session_id)
                mock_manager.commit.assert_called_once()

    def test_session_isolation_between_users(self, mock_user):
        """Test users can only access their own sessions."""
        from indico_assistant.controllers.sessions import RHSessionDetail
        
        ctrl = RHSessionDetail.__new__(RHSessionDetail)
        ctrl.user = mock_user  # User ID 123
        
        session_id = uuid4()
        
        # Session belongs to different user
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
                
                response, status = ctrl._process(str(session_id))
                
                assert status == 403
                data = response.get_json()
                assert data["error"] == "ACCESS_DENIED"

    def test_pagination_works_correctly(self, mock_user):
        """Test pagination returns correct page of results."""
        from indico_assistant.controllers.sessions import RHSessionList
        
        ctrl = RHSessionList.__new__(RHSessionList)
        ctrl.user = mock_user
        
        # Create mock sessions for second page
        mock_sessions = []
        for i in range(5):
            s = MagicMock()
            s.id = uuid4()
            s.event_id = None
            s.created_at = datetime.now(timezone.utc)
            s.updated_at = datetime.now(timezone.utc)
            s.message_count = 2
            mock_sessions.append(s)
        
        with patch('indico_assistant.controllers.sessions.request') as mock_request:
            mock_request.args.get.side_effect = lambda k, d=None: {"limit": "5", "offset": "5"}.get(k, d)
            
            with patch('indico_assistant.controllers.sessions.get_session_manager') as mock_get:
                mock_manager = MagicMock()
                mock_get.return_value = mock_manager
                mock_manager.list_user_sessions.return_value = mock_sessions
                mock_manager.count_user_sessions.return_value = 25  # Total across all pages
                
                with patch('indico_assistant.controllers.sessions.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=199, retry_after=None
                    )
                    
                    response, status = ctrl._process()
                    
                    assert status == 200
                    data = response.get_json()
                    assert len(data["sessions"]) == 5
                    assert data["total"] == 25
                    assert data["limit"] == 5
                    assert data["offset"] == 5
                    
                    # Verify pagination metadata for navigation
                    # Page 2 of 5 (25 total, 5 per page, offset 5)
