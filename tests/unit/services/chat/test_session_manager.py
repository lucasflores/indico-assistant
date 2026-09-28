"""Unit tests for SessionManager service.

Feature: 004-chat-api
Task: T019
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestSessionManager:
    """Tests for SessionManager class."""

    @pytest.fixture
    def session_manager(self):
        """Create a SessionManager instance with mocked db."""
        with patch('indico_assistant.services.chat.session_manager.db') as mock_db:
            from indico_assistant.services.chat.session_manager import SessionManager
            
            mock_db.session = MagicMock()
            manager = SessionManager()
            yield manager

    def test_create_session(self, session_manager):
        """Test creating a new chat session."""
        with patch('indico_assistant.services.chat.session_manager.ChatSession') as mock_cls:
            mock_session = MagicMock()
            mock_session.id = uuid4()
            mock_session.user_id = 123
            mock_session.event_id = None
            mock_cls.create.return_value = mock_session
            
            result = session_manager.create_session(user_id=123)
            
            mock_cls.create.assert_called_once_with(user_id=123, event_id=None)
            assert result == mock_session

    def test_create_session_with_event_id(self, session_manager):
        """Test creating a session with event scope."""
        with patch('indico_assistant.services.chat.session_manager.ChatSession') as mock_cls:
            mock_session = MagicMock()
            mock_session.id = uuid4()
            mock_session.user_id = 123
            mock_session.event_id = 456
            mock_cls.create.return_value = mock_session
            
            result = session_manager.create_session(user_id=123, event_id=456)
            
            mock_cls.create.assert_called_once_with(user_id=123, event_id=456)
            assert result.event_id == 456

    def test_get_session(self, session_manager):
        """Test retrieving a session by ID."""
        session_id = uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        
        with patch('indico_assistant.services.chat.session_manager.ChatSession') as mock_cls:
            mock_cls.query.get.return_value = mock_session
            
            result = session_manager.get_session(session_id)
            
            mock_cls.query.get.assert_called_once_with(session_id)
            assert result == mock_session

    def test_get_session_not_found(self, session_manager):
        """Test retrieving a non-existent session."""
        session_id = uuid4()
        
        with patch('indico_assistant.services.chat.session_manager.ChatSession') as mock_cls:
            mock_cls.query.get.return_value = None
            
            result = session_manager.get_session(session_id)
            
            assert result is None

    def test_get_session_or_create_existing(self, session_manager):
        """Test get_or_create returns existing session."""
        session_id = uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        
        with patch('indico_assistant.services.chat.session_manager.ChatSession') as mock_cls:
            mock_cls.query.get.return_value = mock_session
            
            result, created = session_manager.get_session_or_create(
                session_id=session_id,
                user_id=123
            )
            
            assert result == mock_session
            assert created is False

    def test_get_session_or_create_new(self, session_manager):
        """Test get_or_create creates new session when none exists."""
        with patch('indico_assistant.services.chat.session_manager.ChatSession') as mock_cls:
            mock_session = MagicMock()
            mock_session.id = uuid4()
            mock_cls.create.return_value = mock_session
            mock_cls.query.get.return_value = None
            
            result, created = session_manager.get_session_or_create(
                session_id=None,
                user_id=123
            )
            
            assert result == mock_session
            assert created is True

    def test_validate_session_ownership_valid(self, session_manager):
        """Test ownership validation passes for correct user."""
        mock_session = MagicMock()
        mock_session.user_id = 123
        
        result = session_manager.validate_session_ownership(mock_session, 123)
        
        assert result is True

    def test_validate_session_ownership_invalid(self, session_manager):
        """Test ownership validation fails for wrong user."""
        mock_session = MagicMock()
        mock_session.user_id = 123
        
        result = session_manager.validate_session_ownership(mock_session, 456)
        
        assert result is False

    def test_add_user_message(self, session_manager):
        """Test adding a user message to session."""
        mock_session = MagicMock()
        mock_session.id = uuid4()
        
        with patch('indico_assistant.services.chat.session_manager.ChatMessage') as mock_cls:
            mock_message = MagicMock()
            mock_message.id = uuid4()
            mock_message.role = "user"
            mock_cls.create.return_value = mock_message
            
            result = session_manager.add_user_message(mock_session, "Hello")
            
            mock_cls.create.assert_called_once()
            call_kwargs = mock_cls.create.call_args[1]
            assert call_kwargs['session_id'] == mock_session.id
            assert call_kwargs['role'] == 'user'
            assert call_kwargs['content'] == 'Hello'

    def test_add_assistant_message(self, session_manager):
        """Test adding an assistant message to session."""
        mock_session = MagicMock()
        mock_session.id = uuid4()
        metadata = {"sql": "SELECT * FROM events"}
        
        with patch('indico_assistant.services.chat.session_manager.ChatMessage') as mock_cls:
            mock_message = MagicMock()
            mock_message.id = uuid4()
            mock_message.role = "assistant"
            mock_cls.create.return_value = mock_message
            
            result = session_manager.add_assistant_message(
                mock_session, 
                "Here are your events",
                metadata
            )
            
            mock_cls.create.assert_called_once()
            call_kwargs = mock_cls.create.call_args[1]
            assert call_kwargs['role'] == 'assistant'
            assert call_kwargs['content'] == 'Here are your events'
            assert call_kwargs['metadata'] == metadata

    def test_list_user_sessions(self, session_manager):
        """Test listing sessions for a user."""
        mock_sessions = [MagicMock(), MagicMock()]
        
        with patch('indico_assistant.services.chat.session_manager.ChatSession') as mock_cls:
            mock_query = MagicMock()
            mock_cls.query.filter_by.return_value = mock_query
            mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = mock_sessions
            
            result = session_manager.list_user_sessions(
                user_id=123,
                limit=10,
                offset=0
            )
            
            assert result == mock_sessions

    def test_delete_session(self, session_manager):
        """Test deleting a session."""
        session_id = uuid4()
        mock_session = MagicMock()
        mock_session.id = session_id
        
        with patch('indico_assistant.services.chat.session_manager.ChatSession') as mock_cls:
            mock_cls.query.get.return_value = mock_session
            
            result = session_manager.delete_session(session_id)
            
            assert result is True

    def test_delete_session_not_found(self, session_manager):
        """Test deleting a non-existent session."""
        session_id = uuid4()
        
        with patch('indico_assistant.services.chat.session_manager.ChatSession') as mock_cls:
            mock_cls.query.get.return_value = None
            
            result = session_manager.delete_session(session_id)
            
            assert result is False


class TestGetSessionManager:
    """Tests for get_session_manager factory function."""

    def test_get_session_manager_returns_instance(self):
        """Test factory function returns a SessionManager."""
        with patch('indico_assistant.services.chat.session_manager.db'):
            import indico_assistant.services.chat.session_manager as module
            module._session_manager = None
            
            from indico_assistant.services.chat.session_manager import (
                SessionManager,
                get_session_manager,
            )
            
            manager = get_session_manager()
            
            assert isinstance(manager, SessionManager)

    def test_get_session_manager_returns_same_instance(self):
        """Test factory function returns same instance (singleton)."""
        with patch('indico_assistant.services.chat.session_manager.db'):
            import indico_assistant.services.chat.session_manager as module
            module._session_manager = None
            
            from indico_assistant.services.chat.session_manager import get_session_manager
            
            manager1 = get_session_manager()
            manager2 = get_session_manager()
            
            assert manager1 is manager2
