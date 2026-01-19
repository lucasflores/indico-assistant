"""Integration smoke test for chat pipeline.

Feature: 010-chat-pipeline-integration
Task: T021
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

import indico_assistant.controllers.chat as chat_module
from indico_assistant.services.chat.service import ChatService


class TestChatPipelineSmoke:
    """Smoke tests for chat pipeline wiring."""

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = 321
        return user

    @pytest.fixture
    def chat_controller(self, mock_user):
        from indico_assistant.controllers.chat import RHChat

        controller = RHChat.__new__(RHChat)
        controller.user = mock_user
        return controller

    @pytest.fixture
    def mock_request(self):
        mock_req = MagicMock()
        original_request = getattr(chat_module, "request", None)
        chat_module.request = mock_req
        yield mock_req
        if original_request:
            chat_module.request = original_request

    def test_chat_pipeline_smoke(self, chat_controller, mock_request, mock_user):
        """Should route request through ChatService and return response."""
        session_id = uuid4()
        message_id = uuid4()

        mock_request.get_json.return_value = {"message": "Hello"}

        mock_session_manager = MagicMock()
        mock_context_builder = MagicMock()
        chat_service = ChatService(
            session_manager=mock_session_manager,
            context_builder=mock_context_builder
        )

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.event_id = None
        mock_session_manager.create_session.return_value = mock_session

        mock_user_msg = MagicMock()
        mock_user_msg.id = uuid4()
        mock_session_manager.add_user_message.return_value = mock_user_msg

        mock_assistant_msg = MagicMock()
        mock_assistant_msg.id = message_id
        mock_session_manager.add_assistant_message.return_value = mock_assistant_msg

        mock_context_builder.build_context.return_value = []

        with patch.object(chat_service, "_process_with_nl2sql") as mock_process:
            mock_process.return_value = ("Hello from pipeline", {"sql_generated": None})

            with patch("indico_assistant.controllers.chat.get_chat_service") as mock_get:
                mock_get.return_value = chat_service

                with patch("indico_assistant.controllers.chat.get_rate_limiter") as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult

                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )

                    response, status_code = chat_controller._process()

                    assert status_code == 201
                    data = response.get_json()
                    assert data["response"] == "Hello from pipeline"
                    assert data["session_id"] == str(session_id)
                    assert data["message_id"] == str(message_id)
