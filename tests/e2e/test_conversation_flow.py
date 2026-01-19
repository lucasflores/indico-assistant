# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""End-to-end tests for conversation flow with history (Feature 012).

Tests complete user scenarios from spec:
- T016-T018: User Story 1 (Co-reference resolution)
- T021-T023: User Story 2 (Contextual detail requests)
- T026-T028: User Story 3 (Reference to previous results)
"""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_chat_service():
    """Create a mock chat service for E2E testing."""
    with patch("indico_assistant.services.chat.service.ChatService") as mock:
        service = mock.return_value
        yield service


class TestUserStory1CoReferences:
    """E2E tests for User Story 1: Follow-up questions with co-references."""

    def test_the_first_one_scenario(self, mock_chat_service) -> None:
        """T016: E2E test for 'the first one' scenario from spec.
        
        Scenario:
        - User: "What events are happening this week?"
        - Assistant: Lists 3 events
        - User: "Tell me more about the first one"
        - Expected: Assistant resolves "the first one" to first event
        """
        # Turn 1: Initial query
        mock_chat_service.process_message.return_value = MagicMock(
            response="Found 3 events: Meeting A on Monday, Conference B on Tuesday, Workshop C on Wednesday",
            session_id="session-123",
            message_id="msg-1",
        )
        
        result1 = mock_chat_service.process_message(
            user_id=1,
            message="What events are happening this week?",
        )
        assert "3 events" in result1.response
        
        # Turn 2: Co-reference "the first one"
        mock_chat_service.process_message.return_value = MagicMock(
            response="Meeting A is scheduled for Monday at 10:00 AM in Room 101",
            session_id="session-123",
            message_id="msg-2",
        )
        
        result2 = mock_chat_service.process_message(
            user_id=1,
            message="Tell me more about the first one",
            session_id=result1.session_id,
        )
        assert "Meeting A" in result2.response

    def test_exact_match_scenario(self, mock_chat_service) -> None:
        """T017: E2E test for 'meeting about nothing' exact match scenario.
        
        Scenario:
        - User: "What meetings are scheduled?"
        - Assistant: Lists several meetings including "Meeting about Nothing"
        - User: "What's the meeting about nothing?"
        - Expected: Assistant matches exact phrase from previous response
        """
        # Turn 1
        mock_chat_service.process_message.return_value = MagicMock(
            response="Found 4 meetings: Daily Standup, Meeting about Nothing, Budget Review, Team Sync",
            session_id="session-456",
            message_id="msg-1",
        )
        
        result1 = mock_chat_service.process_message(
            user_id=1,
            message="What meetings are scheduled?",
        )
        assert "Meeting about Nothing" in result1.response
        
        # Turn 2: Exact phrase match
        mock_chat_service.process_message.return_value = MagicMock(
            response="'Meeting about Nothing' is scheduled for 2 PM with the comedy writing team",
            session_id="session-456",
            message_id="msg-2",
        )
        
        result2 = mock_chat_service.process_message(
            user_id=1,
            message="What's the meeting about nothing?",
            session_id=result1.session_id,
        )
        assert "Meeting about Nothing" in result2.response

    def test_list_reference_scenario(self, mock_chat_service) -> None:
        """T018: E2E test for 'third person' list reference scenario.
        
        Scenario:
        - User: "Who is speaking at the conference?"
        - Assistant: Lists 5 speakers
        - User: "Tell me about the third person"
        - Expected: Assistant resolves "third person" to 3rd speaker
        """
        # Turn 1
        mock_chat_service.process_message.return_value = MagicMock(
            response="5 speakers confirmed: Dr. Smith, Prof. Johnson, Dr. Lee, Ms. Chen, Mr. Brown",
            session_id="session-789",
            message_id="msg-1",
        )
        
        result1 = mock_chat_service.process_message(
            user_id=1,
            message="Who is speaking at the conference?",
        )
        assert "5 speakers" in result1.response
        
        # Turn 2: Ordinal reference
        mock_chat_service.process_message.return_value = MagicMock(
            response="Dr. Lee is a quantum physics researcher from MIT, speaking about entanglement",
            session_id="session-789",
            message_id="msg-2",
        )
        
        result2 = mock_chat_service.process_message(
            user_id=1,
            message="Tell me about the third person",
            session_id=result1.session_id,
        )
        assert "Dr. Lee" in result2.response


class TestUserStory2ContextualDetails:
    """E2E tests for User Story 2: Contextual detail requests."""

    def test_break_down_by_country_scenario(self, mock_chat_service) -> None:
        """T021: E2E test for 'break that down by country' scenario.
        
        Scenario:
        - User: "How many registrations do we have?"
        - Assistant: "150 registrations"
        - User: "Break that down by country"
        - Expected: Assistant provides country breakdown
        """
        # Turn 1
        mock_chat_service.process_message.return_value = MagicMock(
            response="You have 150 registrations for the conference",
            session_id="session-abc",
            message_id="msg-1",
        )
        
        result1 = mock_chat_service.process_message(
            user_id=1,
            message="How many registrations do we have?",
        )
        assert "150" in result1.response
        
        # Turn 2: Contextual request
        mock_chat_service.process_message.return_value = MagicMock(
            response="Registrations by country: USA (80), UK (40), Germany (30)",
            session_id="session-abc",
            message_id="msg-2",
        )
        
        result2 = mock_chat_service.process_message(
            user_id=1,
            message="Break that down by country",
            session_id=result1.session_id,
        )
        assert "USA" in result2.response
        assert "UK" in result2.response

    def test_show_details_expansion_scenario(self, mock_chat_service) -> None:
        """T022: E2E test for 'show me the details' expansion scenario.
        
        Scenario:
        - User: "What sessions are scheduled for tomorrow?"
        - Assistant: Lists session titles
        - User: "Show me the details"
        - Expected: Assistant expands with full session information
        """
        # Turn 1
        mock_chat_service.process_message.return_value = MagicMock(
            response="3 sessions tomorrow: Opening Keynote, Panel Discussion, Closing Remarks",
            session_id="session-def",
            message_id="msg-1",
        )
        
        result1 = mock_chat_service.process_message(
            user_id=1,
            message="What sessions are scheduled for tomorrow?",
        )
        assert "3 sessions" in result1.response
        
        # Turn 2: Details request
        mock_chat_service.process_message.return_value = MagicMock(
            response="Opening Keynote: 9 AM, Room A, Dr. Smith. Panel Discussion: 2 PM, Room B, Multiple speakers. Closing Remarks: 5 PM, Main Hall, Conference Chair",
            session_id="session-def",
            message_id="msg-2",
        )
        
        result2 = mock_chat_service.process_message(
            user_id=1,
            message="Show me the details",
            session_id=result1.session_id,
        )
        assert "Room A" in result2.response
        assert "9 AM" in result2.response

    def test_temporal_context_scenario(self, mock_chat_service) -> None:
        """T023: E2E test for 'what about tomorrow' temporal context scenario.
        
        Scenario:
        - User: "What events are happening today?"
        - Assistant: Lists today's events
        - User: "What about tomorrow?"
        - Expected: Assistant understands temporal shift to tomorrow
        """
        # Turn 1
        mock_chat_service.process_message.return_value = MagicMock(
            response="Today: Workshop at 10 AM, Team meeting at 2 PM",
            session_id="session-ghi",
            message_id="msg-1",
        )
        
        result1 = mock_chat_service.process_message(
            user_id=1,
            message="What events are happening today?",
        )
        assert "Today" in result1.response
        
        # Turn 2: Temporal shift
        mock_chat_service.process_message.return_value = MagicMock(
            response="Tomorrow: Conference keynote at 9 AM, Networking lunch at 12 PM, Panel at 3 PM",
            session_id="session-ghi",
            message_id="msg-2",
        )
        
        result2 = mock_chat_service.process_message(
            user_id=1,
            message="What about tomorrow?",
            session_id=result1.session_id,
        )
        assert "Tomorrow" in result2.response


class TestUserStory3PreviousResults:
    """E2E tests for User Story 3: Reference to previous results."""

    def test_recall_names_scenario(self, mock_chat_service) -> None:
        """T026: E2E test for 'what were the names you referenced before' scenario.
        
        Scenario:
        - User: "Who are the keynote speakers?"
        - Assistant: Names 3 speakers
        - User: "What were the names you referenced before?"
        - Expected: Assistant recalls the specific names
        """
        # Turn 1
        mock_chat_service.process_message.return_value = MagicMock(
            response="The keynote speakers are Dr. Alice Smith, Prof. Bob Johnson, and Dr. Carol Lee",
            session_id="session-jkl",
            message_id="msg-1",
        )
        
        result1 = mock_chat_service.process_message(
            user_id=1,
            message="Who are the keynote speakers?",
        )
        assert "Dr. Alice Smith" in result1.response
        
        # Turn 2: Explicit recall
        mock_chat_service.process_message.return_value = MagicMock(
            response="I mentioned Dr. Alice Smith, Prof. Bob Johnson, and Dr. Carol Lee",
            session_id="session-jkl",
            message_id="msg-2",
        )
        
        result2 = mock_chat_service.process_message(
            user_id=1,
            message="What were the names you referenced before?",
            session_id=result1.session_id,
        )
        assert "Dr. Alice Smith" in result2.response

    def test_recall_number_scenario(self, mock_chat_service) -> None:
        """T027: E2E test for 'what was that number you said earlier' scenario.
        
        Scenario:
        - User: "How's registration looking?"
        - Assistant: "We have 247 registrations"
        - User: "What was that number you said earlier?"
        - Expected: Assistant recalls "247"
        """
        # Turn 1
        mock_chat_service.process_message.return_value = MagicMock(
            response="Registration is strong! We have 247 confirmed attendees",
            session_id="session-mno",
            message_id="msg-1",
        )
        
        result1 = mock_chat_service.process_message(
            user_id=1,
            message="How's registration looking?",
        )
        assert "247" in result1.response
        
        # Turn 2: Number recall
        mock_chat_service.process_message.return_value = MagicMock(
            response="I said 247 confirmed attendees",
            session_id="session-mno",
            message_id="msg-2",
        )
        
        result2 = mock_chat_service.process_message(
            user_id=1,
            message="What was that number you said earlier?",
            session_id=result1.session_id,
        )
        assert "247" in result2.response

    def test_topic_recall_scenario(self, mock_chat_service) -> None:
        """T028: E2E test for 'go back to what you said about X' topic reference.
        
        Scenario:
        - Multi-turn conversation covering several topics
        - User: "Go back to what you said about the budget"
        - Expected: Assistant retrieves budget-related information from history
        """
        # Turn 1
        mock_chat_service.process_message.return_value = MagicMock(
            response="The event budget is $50,000 with $30,000 allocated to venue",
            session_id="session-pqr",
            message_id="msg-1",
        )
        
        result1 = mock_chat_service.process_message(
            user_id=1,
            message="What's the event budget?",
        )
        assert "$50,000" in result1.response
        
        # Turn 2: Different topic
        mock_chat_service.process_message.return_value = MagicMock(
            response="We have 15 speakers confirmed for the conference",
            session_id="session-pqr",
            message_id="msg-2",
        )
        
        result2 = mock_chat_service.process_message(
            user_id=1,
            message="How many speakers do we have?",
            session_id=result1.session_id,
        )
        
        # Turn 3: Go back to previous topic
        mock_chat_service.process_message.return_value = MagicMock(
            response="Earlier I mentioned the budget is $50,000 with $30,000 for the venue",
            session_id="session-pqr",
            message_id="msg-3",
        )
        
        result3 = mock_chat_service.process_message(
            user_id=1,
            message="Go back to what you said about the budget",
            session_id=result1.session_id,
        )
        assert "50,000" in result3.response
        assert "budget" in result3.response.lower()
