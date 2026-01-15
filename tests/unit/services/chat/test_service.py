"""Unit tests for ChatService.

Feature: 004-chat-api
Task: T020
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from indico_assistant.services.chat.service import (
    ChatResult,
    ChatService,
    ChatServiceError,
    EventAccessDeniedError,
    QueryProcessingError,
    SessionAccessDeniedError,
    SessionNotFoundError,
)


class TestChatService:
    """Tests for ChatService class."""

    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock session manager."""
        manager = MagicMock()
        manager.commit = MagicMock()
        manager.rollback = MagicMock()
        return manager

    @pytest.fixture
    def mock_context_builder(self):
        """Create a mock context builder."""
        return MagicMock()

    @pytest.fixture
    def chat_service(self, mock_session_manager, mock_context_builder):
        """Create a ChatService with mocked dependencies."""
        return ChatService(
            session_manager=mock_session_manager,
            context_builder=mock_context_builder
        )

    def test_init_with_custom_dependencies(
        self, mock_session_manager, mock_context_builder
    ):
        """Test initialization with custom dependencies."""
        service = ChatService(
            session_manager=mock_session_manager,
            context_builder=mock_context_builder
        )
        
        assert service._session_manager is mock_session_manager
        assert service._context_builder is mock_context_builder

    def test_process_message_creates_new_session(
        self, chat_service, mock_session_manager, mock_context_builder
    ):
        """Test processing a message creates new session when none provided."""
        session_id = uuid4()
        message_id = uuid4()
        
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.event_id = None
        mock_session_manager.create_session.return_value = mock_session
        mock_session_manager.get_session.return_value = None
        
        mock_user_msg = MagicMock()
        mock_user_msg.id = uuid4()
        mock_session_manager.add_user_message.return_value = mock_user_msg
        
        mock_assistant_msg = MagicMock()
        mock_assistant_msg.id = message_id
        mock_session_manager.add_assistant_message.return_value = mock_assistant_msg
        
        mock_context_builder.build_context.return_value = []
        
        with patch.object(chat_service, '_process_with_nl2sql') as mock_process:
            mock_process.return_value = ("Test response", {"sql": "SELECT 1"})
            
            result = chat_service.process_message(
                user_id=123,
                message="What is today?",
                session_id=None
            )
            
            assert isinstance(result, ChatResult)
            assert result.session_id == session_id
            assert result.message_id == message_id
            assert result.response == "Test response"
            assert result.created_session is True
            mock_session_manager.create_session.assert_called_once_with(123, None)

    def test_process_message_uses_existing_session(
        self, chat_service, mock_session_manager, mock_context_builder
    ):
        """Test processing a message uses existing session when provided."""
        session_id = uuid4()
        
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.event_id = None
        mock_session_manager.get_session.return_value = mock_session
        mock_session_manager.validate_session_ownership.return_value = True
        
        mock_user_msg = MagicMock()
        mock_user_msg.id = uuid4()
        mock_session_manager.add_user_message.return_value = mock_user_msg
        
        mock_assistant_msg = MagicMock()
        mock_assistant_msg.id = uuid4()
        mock_session_manager.add_assistant_message.return_value = mock_assistant_msg
        
        mock_context_builder.build_context.return_value = []
        
        with patch.object(chat_service, '_process_with_nl2sql') as mock_process:
            mock_process.return_value = ("Response", {})
            
            result = chat_service.process_message(
                user_id=123,
                message="Follow up question",
                session_id=session_id
            )
            
            assert result.created_session is False
            mock_session_manager.get_session.assert_called_once_with(session_id)

    def test_process_message_session_not_found(
        self, chat_service, mock_session_manager
    ):
        """Test error when session ID provided but not found."""
        session_id = uuid4()
        mock_session_manager.get_session.return_value = None
        
        with pytest.raises(SessionNotFoundError):
            chat_service.process_message(
                user_id=123,
                message="Test",
                session_id=session_id
            )
        
        mock_session_manager.rollback.assert_called_once()

    def test_process_message_session_access_denied(
        self, chat_service, mock_session_manager
    ):
        """Test error when user doesn't own the session."""
        session_id = uuid4()
        
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session_manager.get_session.return_value = mock_session
        mock_session_manager.validate_session_ownership.return_value = False
        
        with pytest.raises(SessionAccessDeniedError):
            chat_service.process_message(
                user_id=123,
                message="Test",
                session_id=session_id
            )
        
        mock_session_manager.rollback.assert_called_once()

    def test_process_message_event_access_validated(
        self, chat_service, mock_session_manager, mock_context_builder
    ):
        """Test that event access is validated for event-scoped sessions."""
        session_id = uuid4()
        
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.event_id = 456
        mock_session_manager.create_session.return_value = mock_session
        
        mock_user_msg = MagicMock()
        mock_session_manager.add_user_message.return_value = mock_user_msg
        
        mock_assistant_msg = MagicMock()
        mock_assistant_msg.id = uuid4()
        mock_session_manager.add_assistant_message.return_value = mock_assistant_msg
        
        mock_context_builder.build_context.return_value = []
        
        with patch.object(chat_service, '_validate_event_access') as mock_validate:
            with patch.object(chat_service, '_process_with_nl2sql') as mock_process:
                mock_process.return_value = ("Response", {})
                
                chat_service.process_message(
                    user_id=123,
                    message="What events?",
                    event_id=456
                )
                
                mock_validate.assert_called_once_with(123, 456)

    def test_process_message_commits_on_success(
        self, chat_service, mock_session_manager, mock_context_builder
    ):
        """Test that transaction is committed on success."""
        mock_session = MagicMock()
        mock_session.id = uuid4()
        mock_session.event_id = None
        mock_session_manager.create_session.return_value = mock_session
        
        mock_user_msg = MagicMock()
        mock_session_manager.add_user_message.return_value = mock_user_msg
        
        mock_assistant_msg = MagicMock()
        mock_assistant_msg.id = uuid4()
        mock_session_manager.add_assistant_message.return_value = mock_assistant_msg
        
        mock_context_builder.build_context.return_value = []
        
        with patch.object(chat_service, '_process_with_nl2sql') as mock_process:
            mock_process.return_value = ("Response", {})
            
            chat_service.process_message(user_id=123, message="Test")
            
            mock_session_manager.commit.assert_called_once()

    def test_process_message_rolls_back_on_error(
        self, chat_service, mock_session_manager, mock_context_builder
    ):
        """Test that transaction is rolled back on error."""
        mock_session = MagicMock()
        mock_session.id = uuid4()
        mock_session.event_id = None
        mock_session_manager.create_session.return_value = mock_session
        
        mock_user_msg = MagicMock()
        mock_session_manager.add_user_message.return_value = mock_user_msg
        
        mock_context_builder.build_context.return_value = []
        
        with patch.object(chat_service, '_process_with_nl2sql') as mock_process:
            mock_process.side_effect = Exception("Processing error")
            
            with pytest.raises(QueryProcessingError):
                chat_service.process_message(user_id=123, message="Test")
            
            mock_session_manager.rollback.assert_called_once()


class TestChatResult:
    """Tests for ChatResult dataclass."""

    def test_chat_result_creation(self):
        """Test creating a ChatResult."""
        session_id = uuid4()
        message_id = uuid4()
        
        result = ChatResult(
            response="Test response",
            session_id=session_id,
            message_id=message_id,
            metadata={"sql": "SELECT 1"}
        )
        
        assert result.response == "Test response"
        assert result.session_id == session_id
        assert result.message_id == message_id
        assert result.metadata == {"sql": "SELECT 1"}
        assert result.created_session is False

    def test_chat_result_with_created_session(self):
        """Test ChatResult with created_session flag."""
        result = ChatResult(
            response="Test",
            session_id=uuid4(),
            message_id=uuid4(),
            metadata={},
            created_session=True
        )
        
        assert result.created_session is True


class TestExceptions:
    """Tests for chat service exceptions."""

    def test_session_not_found_error(self):
        """Test SessionNotFoundError."""
        error = SessionNotFoundError("Session abc not found")
        assert str(error) == "Session abc not found"
        assert isinstance(error, ChatServiceError)

    def test_session_access_denied_error(self):
        """Test SessionAccessDeniedError."""
        error = SessionAccessDeniedError("Not your session")
        assert str(error) == "Not your session"
        assert isinstance(error, ChatServiceError)

    def test_event_access_denied_error(self):
        """Test EventAccessDeniedError with event_id."""
        error = EventAccessDeniedError(456, "Cannot access")
        assert error.event_id == 456
        assert str(error) == "Cannot access"
        assert isinstance(error, ChatServiceError)

    def test_query_processing_error(self):
        """Test QueryProcessingError with reason."""
        error = QueryProcessingError("Query failed", reason="timeout")
        assert str(error) == "Query failed"
        assert error.reason == "timeout"
        assert isinstance(error, ChatServiceError)


class TestGetChatService:
    """Tests for get_chat_service factory function."""

    def test_get_chat_service_returns_instance(self):
        """Test factory function returns a ChatService."""
        with patch('indico_assistant.services.chat.service.get_session_manager'):
            with patch('indico_assistant.services.chat.service.get_context_builder'):
                import indico_assistant.services.chat.service as module
                module._chat_service = None
                
                from indico_assistant.services.chat.service import (
                    ChatService,
                    get_chat_service,
                )
                
                service = get_chat_service()
                
                assert isinstance(service, ChatService)

    def test_get_chat_service_returns_same_instance(self):
        """Test factory function returns same instance (singleton)."""
        with patch('indico_assistant.services.chat.service.get_session_manager'):
            with patch('indico_assistant.services.chat.service.get_context_builder'):
                import indico_assistant.services.chat.service as module
                module._chat_service = None
                
                from indico_assistant.services.chat.service import get_chat_service
                
                service1 = get_chat_service()
                service2 = get_chat_service()
                
                assert service1 is service2
