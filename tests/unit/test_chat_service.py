"""Unit tests for chat service NL2SQL integration.

Feature: 010-chat-pipeline-integration
Task: T022
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from indico_assistant.services.chat.service import ChatService
from indico_assistant.services.nl2sql.models import PipelineResult


def test_process_with_nl2sql_uses_pipeline_factory():
    """Ensure ChatService uses pipeline factory and returns metadata."""
    service = ChatService(
        session_manager=MagicMock(),
        context_builder=MagicMock()
    )

    pipeline = MagicMock()
    pipeline.process.return_value = PipelineResult(
        success=True,
        answer="Pipeline response",
        generated_sql="SELECT 1",
        tables_accessed=["events"],
        confidence=0.9,
    )

    mock_plugin = MagicMock()
    mock_plugin.settings.get.side_effect = lambda k, default=None: (
        False if k == "vector_search_enabled" else default
    )

    with patch("indico_assistant.services.chat.service.AssistantPlugin") as mock_plugin_cls:
        mock_plugin_cls.instance = mock_plugin
        with patch(
            "indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin"
        ) as mock_factory:
            mock_factory.return_value = pipeline

            response_text, metadata = service._process_with_nl2sql(
                message="Hello",
                context=[],
                event_id=None,
                user_id=123
            )

            mock_factory.assert_called_once_with(mock_plugin)
            pipeline.process.assert_called_once_with(
                question="Hello",
                user_id=123,
                event_ids=None,
            )

            assert response_text == "Pipeline response"
            assert metadata["sql_generated"] == "SELECT 1"
            assert metadata["data_sources"] == ["events"]
            assert metadata["confidence"] == 0.9
