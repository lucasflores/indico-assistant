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

    @pytest.fixture
    def user(self):
        return MagicMock(id=123, is_admin=False)

    def test_submit_creates_session_saves_message_and_commits(self, chat_service, mock_session_manager, user):
        session = MagicMock(id=uuid4(), event_id=None)
        mock_session_manager.create_session.return_value = session

        assert chat_service.submit_message(user, "What events?") == (session.id, True)
        mock_session_manager.create_session.assert_called_once_with(123, None)
        mock_session_manager.add_user_message.assert_called_once_with(session, "What events?")
        mock_session_manager.commit.assert_called_once()

    def test_submit_to_existing_session(self, chat_service, mock_session_manager, user):
        session = MagicMock(id=uuid4(), event_id=None)
        mock_session_manager.get_session.return_value = session
        mock_session_manager.validate_session_ownership.return_value = True

        assert chat_service.submit_message(user, "and then?", session_id=session.id) == (session.id, False)
        mock_session_manager.create_session.assert_not_called()

    def test_submit_unknown_session(self, chat_service, mock_session_manager, user):
        mock_session_manager.get_session.return_value = None
        with pytest.raises(SessionNotFoundError):
            chat_service.submit_message(user, "hi", session_id=uuid4())
        mock_session_manager.rollback.assert_called_once()

    def test_submit_someone_elses_session(self, chat_service, mock_session_manager, user):
        mock_session_manager.get_session.return_value = MagicMock()
        mock_session_manager.validate_session_ownership.return_value = False
        with pytest.raises(SessionAccessDeniedError):
            chat_service.submit_message(user, "hi", session_id=uuid4())
        mock_session_manager.add_user_message.assert_not_called()

    def test_submit_checks_event_access_before_saving(self, chat_service, mock_session_manager, user):
        mock_session_manager.create_session.return_value = MagicMock(event_id=456)
        with patch.object(chat_service, '_validate_event_access',
                          side_effect=EventAccessDeniedError(456)) as validate:
            with pytest.raises(EventAccessDeniedError):
                chat_service.submit_message(user, "hi", event_id=456)
        validate.assert_called_once_with(user, 456)
        mock_session_manager.add_user_message.assert_not_called()

    def test_answer_runs_pipeline_as_the_user_with_no_transaction_open(
        self, chat_service, mock_session_manager, mock_context_builder
    ):
        session_id = uuid4()
        mock_session_manager.get_session.return_value = MagicMock(id=session_id, event_id=456)
        mock_session_manager.add_assistant_message.return_value = MagicMock(id=uuid4())
        mock_context_builder.build_context.return_value = [{"role": "user", "content": "hi"}]
        user = MagicMock(id=123, is_admin=True)
        calls = []

        def pipeline(message, context, event_id, user_id=None, auth_user=None):
            calls.append('pipeline')
            assert (auth_user.id, auth_user.is_admin, event_id, user_id) == (123, True, 456, 123)
            return "Answer", {"confidence": 0.9}

        with patch.object(chat_service, '_load_user', return_value=user), \
                patch.object(chat_service, '_process_with_nl2sql', side_effect=pipeline), \
                patch('indico_assistant.services.chat.service.db') as db:
            db.session.commit.side_effect = lambda: calls.append('commit')
            result = chat_service.answer(123, session_id, "hi")

        assert calls == ['commit', 'pipeline']  # reads committed before any LLM call
        assert result.response == "Answer" and result.session_id == session_id
        mock_session_manager.add_assistant_message.assert_called_once()
        mock_session_manager.commit.assert_called_once()

    def test_answer_for_vanished_session(self, chat_service, mock_session_manager):
        mock_session_manager.get_session.return_value = None
        with patch.object(chat_service, '_load_user', return_value=MagicMock()):
            with pytest.raises(SessionNotFoundError):
                chat_service.answer(123, uuid4(), "hi")


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
