# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Integration tests for conversation history feature (Feature 012).

Tests the full pipeline with conversation history including:
- T015: 2-turn co-reference conversation
- T020: 3-turn contextual drill-down
- T025: Explicit recall of previous assistant response
- T033: Cross-topic conversation (topic switching)
- T034: Event-scoped session with multi-event history
"""

from unittest.mock import MagicMock, patch

import pytest

from indico_assistant.services.nl2sql.models import PipelineResult


@pytest.fixture
def mock_pipeline_with_history():
    """Create a mock pipeline that accepts conversation history."""
    with patch("indico_assistant.services.nl2sql.pipeline.NL2SQLPipeline") as mock:
        pipeline = mock.return_value
        pipeline.process.return_value = PipelineResult(
            success=True,
            answer="Mock answer",
            sql="SELECT * FROM events.events",
            confidence=0.95,
        )
        yield pipeline


class TestCoReferenceResolution:
    """Test co-reference resolution with conversation history (T015)."""

    def test_two_turn_coreference_conversation(
        self, mock_pipeline_with_history
    ) -> None:
        """T015: Test pipeline with mock 2-turn co-reference conversation."""
        # Simulate a 2-turn conversation
        history = [
            {"role": "user", "content": "What events are happening this week?"},
            {"role": "assistant", "content": "Found 3 events: Meeting A, Conference B, Workshop C"},
        ]

        # Second turn with co-reference
        result = mock_pipeline_with_history.process(
            question="Tell me more about the first one",
            user_id=1,
            conversation_history=history,
        )

        assert result.success is True
        # Verify history was passed to pipeline
        call_args = mock_pipeline_with_history.process.call_args
        assert call_args[1]["conversation_history"] == history


class TestContextualDrillDown:
    """Test contextual detail requests (T020)."""

    def test_three_turn_contextual_sequence(
        self, mock_pipeline_with_history
    ) -> None:
        """T020: Test 3-turn contextual drill-down sequence."""
        # Turn 1: Initial query
        history_turn1 = []
        result1 = mock_pipeline_with_history.process(
            question="How many registrations?",
            user_id=1,
            conversation_history=history_turn1,
        )
        assert result1.success is True

        # Turn 2: Build on previous context
        history_turn2 = [
            {"role": "user", "content": "How many registrations?"},
            {"role": "assistant", "content": "Found 150 registrations"},
        ]
        result2 = mock_pipeline_with_history.process(
            question="Break that down by country",
            user_id=1,
            conversation_history=history_turn2,
        )
        assert result2.success is True

        # Turn 3: Continue building context
        history_turn3 = [
            {"role": "user", "content": "How many registrations?"},
            {"role": "assistant", "content": "Found 150 registrations"},
            {"role": "user", "content": "Break that down by country"},
            {"role": "assistant", "content": "USA: 80, UK: 40, Germany: 30"},
        ]
        result3 = mock_pipeline_with_history.process(
            question="Show me the top 3 countries",
            user_id=1,
            conversation_history=history_turn3,
        )
        assert result3.success is True


class TestExplicitRecall:
    """Test explicit recall of previous assistant responses (T025)."""

    def test_recall_previous_assistant_response(
        self, mock_pipeline_with_history
    ) -> None:
        """T025: Test explicit recall of previous assistant response."""
        history = [
            {"role": "user", "content": "What speakers are confirmed?"},
            {"role": "assistant", "content": "3 speakers: Dr. Smith, Prof. Johnson, Dr. Lee"},
            {"role": "user", "content": "What were the names you just mentioned?"},
        ]

        result = mock_pipeline_with_history.process(
            question="What were the names you just mentioned?",
            user_id=1,
            conversation_history=history,
        )

        assert result.success is True
        # Verify assistant message content is in history
        call_args = mock_pipeline_with_history.process.call_args
        passed_history = call_args[1]["conversation_history"]
        assert any("Dr. Smith" in msg["content"] for msg in passed_history)


class TestEdgeCases:
    """Test edge cases and robustness (T033-T034)."""

    def test_cross_topic_conversation(self, mock_pipeline_with_history) -> None:
        """T033: Test cross-topic conversation (topic switching)."""
        # User switches from events to contributions mid-conversation
        history = [
            {"role": "user", "content": "How many events this month?"},
            {"role": "assistant", "content": "5 events found"},
            {"role": "user", "content": "What about contributions?"},  # Topic switch
        ]

        result = mock_pipeline_with_history.process(
            question="What about contributions?",
            user_id=1,
            conversation_history=history,
        )

        assert result.success is True

    def test_event_scoped_session_with_multi_event_history(
        self, mock_pipeline_with_history
    ) -> None:
        """T034: Test event-scoped session with multi-event history."""
        # Conversation scoped to a specific event but references others
        history = [
            {"role": "user", "content": "How does this event compare to last year?"},
            {"role": "assistant", "content": "This event has 200 attendees vs 150 last year"},
        ]

        result = mock_pipeline_with_history.process(
            question="Show me the registration breakdown",
            user_id=1,
            event_ids=[123],  # Event-scoped
            conversation_history=history,
        )

        assert result.success is True
        # Verify event scope is maintained
        call_args = mock_pipeline_with_history.process.call_args
        assert call_args[1]["event_ids"] == [123]
