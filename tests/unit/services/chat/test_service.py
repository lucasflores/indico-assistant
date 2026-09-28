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

        assert chat_service.submit_message(user, "What events?") == (
            session.id, True, mock_session_manager.add_user_message.return_value.id)
        mock_session_manager.create_session.assert_called_once_with(123, None)
        mock_session_manager.add_user_message.assert_called_once_with(session, "What events?", {"event_id": None})
        mock_session_manager.commit.assert_called_once()

    def test_submit_to_existing_session(self, chat_service, mock_session_manager, user):
        session = MagicMock(id=uuid4(), event_id=None)
        mock_session_manager.get_session.return_value = session
        mock_session_manager.validate_session_ownership.return_value = True

        assert chat_service.submit_message(user, "and then?", session_id=session.id)[:2] == (session.id, False)
        mock_session_manager.create_session.assert_not_called()

    def test_submit_unknown_session_starts_it_under_that_id(self, chat_service, mock_session_manager, user):
        # spec 020 R5: the chat panel's thread id becomes the session id
        mock_session_manager.get_session.return_value = None
        mock_session_manager.create_session.return_value = MagicMock(event_id=None)
        thread_id = uuid4()
        chat_service.submit_message(user, "hi", session_id=thread_id)
        mock_session_manager.create_session.assert_called_once_with(user.id, None, session_id=thread_id)

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
        mock_session_manager.page_event_of.side_effect = lambda message_id, fallback: fallback  # (spec 020)
        mock_session_manager.add_assistant_message.return_value = MagicMock(id=uuid4())
        mock_context_builder.build_context.return_value = [{"role": "user", "content": "hi"}]
        user = MagicMock(id=123, is_admin=True)
        calls = []

        def pipeline(message, context, event_id, user_id=None, auth_user=None):
            calls.append('pipeline')
            assert (auth_user.id, auth_user.is_admin, event_id, user_id) == (123, True, 456, 123)
            return "Answer", {"confidence": 0.9}

        with patch.object(chat_service, '_load_user', return_value=user), \
                patch.object(chat_service, '_validate_event_access') as validate, \
                patch.object(chat_service, '_process_with_nl2sql', side_effect=pipeline), \
                patch('indico_assistant.services.chat.service.db') as db:
            db.session.commit.side_effect = lambda: calls.append('commit')
            result = chat_service.answer(123, session_id, "hi", message_id="q1")

        assert calls == ['commit', 'pipeline']  # reads committed before any LLM call
        validate.assert_called_once_with(user, 456)
        # a question sent while this one was queued is not in its context
        mock_context_builder.build_context.assert_called_once_with(session_id, up_to="q1")
        assert result.response == "Answer" and result.session_id == session_id
        mock_session_manager.add_assistant_message.assert_called_once()
        mock_session_manager.commit.assert_called_once()

    def test_submit_refuses_another_event_scope(self, chat_service, mock_session_manager, user):
        mock_session_manager.get_session.return_value = MagicMock(event_id=None)
        mock_session_manager.validate_session_ownership.return_value = True
        with pytest.raises(EventAccessDeniedError):
            chat_service.submit_message(user, "hi", session_id=uuid4(), event_id=456)
        mock_session_manager.add_user_message.assert_not_called()

    def test_answer_refuses_if_access_was_revoked_while_queued(self, chat_service, mock_session_manager):
        mock_session_manager.get_session.return_value = MagicMock(event_id=456)
        with patch.object(chat_service, '_load_user', return_value=MagicMock()), \
                patch.object(chat_service, '_validate_event_access', side_effect=EventAccessDeniedError(456)), \
                patch.object(chat_service, '_process_with_nl2sql') as pipeline:
            with pytest.raises(EventAccessDeniedError):
                chat_service.answer(123, uuid4(), "hi")
        pipeline.assert_not_called()

    # --- spec 020 US2: "this event" is the page each message is sent from -----------------------------

    def test_a_message_from_another_events_page_is_accepted(self, chat_service, mock_session_manager, user):
        session = MagicMock(id=uuid4(), event_id=351)  # started on event 351
        mock_session_manager.get_session.return_value = session
        mock_session_manager.validate_session_ownership.return_value = True
        with patch.object(chat_service, '_validate_event_access') as check:
            chat_service.submit_message(user, "and this one?", session_id=session.id, event_id=352)
        check.assert_called_once_with(user, 352)  # the page's event, not the one it started on
        mock_session_manager.add_user_message.assert_called_once_with(session, "and this one?", {"event_id": 352})

    def test_access_is_checked_against_the_messages_page(self, chat_service, mock_session_manager, user):
        session = MagicMock(id=uuid4(), event_id=351)
        mock_session_manager.get_session.return_value = session
        mock_session_manager.validate_session_ownership.return_value = True
        with patch.object(chat_service, '_validate_event_access', side_effect=EventAccessDeniedError(352)):
            with pytest.raises(EventAccessDeniedError):
                chat_service.submit_message(user, "hi", session_id=session.id, event_id=352)
        mock_session_manager.add_user_message.assert_not_called()

    def test_the_answer_is_for_the_questions_page(self, chat_service, mock_session_manager, mock_context_builder):
        session_id, message_id = uuid4(), uuid4()
        mock_session_manager.get_session.return_value = MagicMock(id=session_id, event_id=351)
        mock_session_manager.page_event_of.return_value = 352
        mock_session_manager.add_assistant_message.return_value = MagicMock(id=uuid4())
        mock_context_builder.build_context.return_value = [{"role": "user", "content": "hi"}]
        mock_context_builder.page_note.return_value = {"role": "system", "content": "page 352"}
        nl2sql = MagicMock(return_value=("An answer", {}))
        with patch.object(chat_service, '_load_user', return_value=MagicMock(id=123, is_admin=False)), \
                patch.object(chat_service, '_validate_event_access') as check, \
                patch.object(chat_service, '_process_with_nl2sql', nl2sql), \
                patch('indico_assistant.services.actions.executor.open_plan', return_value=None), \
                patch('indico_assistant.services.chat.service.db'):
            chat_service.answer(123, session_id, "hi", message_id)
        mock_session_manager.page_event_of.assert_called_once_with(message_id, 351)
        assert check.call_args.args[1] == 352 and nl2sql.call_args.args[2] == 352
        history = nl2sql.call_args.args[1]
        assert history[-2] == {"role": "system", "content": "page 352"} and history[-1]["content"] == "hi"

    @pytest.fixture
    def routed(self, chat_service, mock_session_manager, mock_context_builder):
        """answer() with the planner and NL2SQL stubbed; returns (run, plan stub, nl2sql stub)."""
        session_id = uuid4()
        mock_session_manager.get_session.return_value = MagicMock(id=session_id, event_id=None)
        mock_session_manager.add_assistant_message.return_value = MagicMock(id=uuid4())
        mock_context_builder.build_context.return_value = [{"role": "user", "content": "hi"}]
        plan, nl2sql, waiting = MagicMock(), MagicMock(return_value=("An answer", {})), MagicMock()

        def run(waiting_plan=None):
            waiting.return_value = waiting_plan
            with patch.object(chat_service, '_load_user', return_value=MagicMock(id=123, is_admin=False)), \
                    patch.object(chat_service, '_plan', plan), \
                    patch.object(chat_service, '_process_with_nl2sql', nl2sql), \
                    patch('indico_assistant.services.actions.executor.open_plan', waiting), \
                    patch('indico_assistant.services.chat.service.db'):
                return chat_service.answer(123, session_id, "hi")
        return run, plan, nl2sql

    def test_a_follow_up_on_an_open_plan_goes_to_the_planner(self, routed):
        run, plan, nl2sql = routed
        plan.return_value = ("Updated the plan.", {"plan_id": "p2"}, {"id": "p2"})
        result = run(waiting_plan=MagicMock())
        assert (result.response, result.plan) == ("Updated the plan.", {"id": "p2"})
        nl2sql.assert_not_called()

    def test_a_question_despite_an_open_plan_goes_to_nl2sql(self, routed):
        run, plan, nl2sql = routed
        plan.return_value = None  # the planner said "unrelated"
        assert run(waiting_plan=MagicMock()).response == "An answer"
        nl2sql.assert_called_once()

    def test_a_change_request_goes_to_the_planner(self, routed):
        run, plan, nl2sql = routed
        nl2sql.return_value = ("", {"write_request": True})
        plan.return_value = ("Here is the plan.", {"plan_id": "p1"}, {"id": "p1"})
        result = run()
        assert result.plan == {"id": "p1"} and plan.call_args.args[-1] is None  # no open plan

    def test_a_change_request_the_planner_turns_down_still_gets_a_reply(self, routed):
        # (code review, PR #3) NL2SQL said write_request, the planner said "unrelated": never a blank bubble
        from indico_assistant.services.actions.planner import NOT_UNDERSTOOD
        run, plan, nl2sql = routed
        nl2sql.return_value = ("", {"write_request": True})
        plan.return_value = None
        assert run().response == NOT_UNDERSTOOD

    def test_questions_never_reach_the_planner(self, routed):
        run, plan, nl2sql = routed
        assert run().plan is None
        plan.assert_not_called()

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
