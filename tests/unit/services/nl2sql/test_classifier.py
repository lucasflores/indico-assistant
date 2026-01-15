# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Unit tests for QueryClassifier component."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from indico_assistant.services.nl2sql.classifier import QueryClassifier


@pytest.fixture
def mock_llm_service() -> MagicMock:
    """Create a mock LLM service."""
    return MagicMock()


@pytest.fixture
def mock_classification() -> MagicMock:
    """Create a mock QueryClassification."""
    classification = MagicMock()
    classification.intent = "event_query"
    classification.entities = ["Physics Conference"]
    classification.time_range = None
    return classification


@pytest.fixture
def mock_llm_response(mock_classification: MagicMock) -> MagicMock:
    """Create a mock LLM response."""
    response = MagicMock()
    response.success = True
    response.data = mock_classification
    return response


@pytest.fixture
def classifier(
    mock_llm_service: MagicMock, mock_llm_response: MagicMock
) -> QueryClassifier:
    """Create a classifier instance."""
    mock_llm_service.generate.return_value = mock_llm_response
    return QueryClassifier(llm_service=mock_llm_service)


class TestQueryClassifierBasicClassification:
    """Test basic classification functionality."""

    def test_classify_event_query(
        self, classifier: QueryClassifier, mock_llm_service: MagicMock
    ) -> None:
        """Should classify event query."""
        result = classifier.classify("How many events are there?")

        assert result.success is True
        assert result.data is not None
        mock_llm_service.generate.assert_called_once()

    def test_classify_passes_question_to_prompt(
        self, classifier: QueryClassifier, mock_llm_service: MagicMock
    ) -> None:
        """Question should be included in the prompt."""
        question = "List all physics conferences"
        classifier.classify(question)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert question in prompt

    def test_classify_includes_today_date(
        self, classifier: QueryClassifier, mock_llm_service: MagicMock
    ) -> None:
        """Today's date should be included in prompt."""
        today = datetime.now().strftime("%Y-%m-%d")
        classifier.classify("What events are coming up?")

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert today in prompt

    def test_classify_uses_correct_response_model(
        self, classifier: QueryClassifier, mock_llm_service: MagicMock
    ) -> None:
        """Should use QueryClassification response model."""
        classifier.classify("List events")

        call_args = mock_llm_service.generate.call_args
        assert "response_model" in call_args[1]


class TestQueryClassifierTimeReferenceDefaults:
    """Test time reference resolution (FR-003, FR-040)."""

    def test_recently_resolves_to_7_days_back(
        self,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """'recently' should resolve to last 7 days."""
        mock_classification.time_range = None
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        result = classifier.classify("What events happened recently?")

        assert result.data.time_range is not None
        today = datetime.now()
        expected_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        expected_end = today.strftime("%Y-%m-%d")
        assert result.data.time_range.start == expected_start
        assert result.data.time_range.end == expected_end

    def test_lately_resolves_to_7_days_back(
        self,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """'lately' should resolve to last 7 days."""
        mock_classification.time_range = None
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        result = classifier.classify("What events were created lately?")

        assert result.data.time_range is not None
        today = datetime.now()
        expected_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        assert result.data.time_range.start == expected_start

    def test_soon_resolves_to_7_days_forward(
        self,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """'soon' should resolve to next 7 days."""
        mock_classification.time_range = None
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        result = classifier.classify("What events are happening soon?")

        assert result.data.time_range is not None
        today = datetime.now()
        expected_start = today.strftime("%Y-%m-%d")
        expected_end = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        assert result.data.time_range.start == expected_start
        assert result.data.time_range.end == expected_end

    def test_upcoming_resolves_to_7_days_forward(
        self,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """'upcoming' should resolve to next 7 days."""
        mock_classification.time_range = None
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        result = classifier.classify("Show upcoming events")

        assert result.data.time_range is not None
        today = datetime.now()
        expected_end = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        assert result.data.time_range.end == expected_end

    def test_a_while_ago_resolves_to_30_days_back(
        self,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """'a while ago' should resolve to last 30 days."""
        mock_classification.time_range = None
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        result = classifier.classify("What events happened a while ago?")

        assert result.data.time_range is not None
        today = datetime.now()
        expected_start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        assert result.data.time_range.start == expected_start

    def test_this_week_resolves_to_current_week(
        self,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """'this week' should resolve to Monday-Sunday of current week."""
        mock_classification.time_range = None
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        result = classifier.classify("What events are happening this week?")

        assert result.data.time_range is not None
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        expected_start = start_of_week.strftime("%Y-%m-%d")
        expected_end = end_of_week.strftime("%Y-%m-%d")
        assert result.data.time_range.start == expected_start
        assert result.data.time_range.end == expected_end

    def test_last_week_resolves_to_previous_week(
        self,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """'last week' should resolve to 7 days back."""
        mock_classification.time_range = None
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        result = classifier.classify("What happened last week?")

        assert result.data.time_range is not None
        today = datetime.now()
        expected_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        assert result.data.time_range.start == expected_start

    def test_next_week_resolves_to_coming_week(
        self,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """'next week' should resolve to 7 days forward."""
        mock_classification.time_range = None
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        result = classifier.classify("What events are next week?")

        assert result.data.time_range is not None
        today = datetime.now()
        expected_end = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        assert result.data.time_range.end == expected_end


class TestQueryClassifierTimeRangePreservation:
    """Test that LLM time ranges are preserved."""

    def test_llm_time_range_not_overwritten(
        self,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """LLM-provided time_range should not be overwritten."""
        # LLM provides a specific time range
        mock_time_range = MagicMock()
        mock_time_range.start = "2024-06-01"
        mock_time_range.end = "2024-06-30"
        mock_classification.time_range = mock_time_range
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        result = classifier.classify("What happened recently in June?")

        # Original time range should be preserved
        assert result.data.time_range.start == "2024-06-01"
        assert result.data.time_range.end == "2024-06-30"


class TestQueryClassifierOutOfScope:
    """Test out-of-scope detection."""

    def test_is_out_of_scope_true(self) -> None:
        """Should return True for out_of_scope intent."""
        classification = MagicMock()
        classification.intent = "out_of_scope"

        classifier = QueryClassifier(llm_service=MagicMock())
        result = classifier.is_out_of_scope(classification)

        assert result is True

    def test_is_out_of_scope_false_for_event_query(self) -> None:
        """Should return False for event_query intent."""
        classification = MagicMock()
        classification.intent = "event_query"

        classifier = QueryClassifier(llm_service=MagicMock())
        result = classifier.is_out_of_scope(classification)

        assert result is False

    def test_is_out_of_scope_false_for_registration_query(self) -> None:
        """Should return False for registration_query intent."""
        classification = MagicMock()
        classification.intent = "registration_query"

        classifier = QueryClassifier(llm_service=MagicMock())
        result = classifier.is_out_of_scope(classification)

        assert result is False

    def test_is_out_of_scope_false_for_contribution_query(self) -> None:
        """Should return False for contribution_query intent."""
        classification = MagicMock()
        classification.intent = "contribution_query"

        classifier = QueryClassifier(llm_service=MagicMock())
        result = classifier.is_out_of_scope(classification)

        assert result is False

    def test_is_out_of_scope_false_for_general_info(self) -> None:
        """Should return False for general_info intent."""
        classification = MagicMock()
        classification.intent = "general_info"

        classifier = QueryClassifier(llm_service=MagicMock())
        result = classifier.is_out_of_scope(classification)

        assert result is False


class TestQueryClassifierFailedResponse:
    """Test handling of failed LLM responses."""

    def test_failed_response_returned(
        self, mock_llm_service: MagicMock
    ) -> None:
        """Failed LLM response should be returned as-is."""
        failed_response = MagicMock()
        failed_response.success = False
        failed_response.data = None
        failed_response.error = "LLM error"
        mock_llm_service.generate.return_value = failed_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        result = classifier.classify("Some question")

        assert result.success is False
        assert result.data is None

    def test_time_reference_skipped_on_failure(
        self, mock_llm_service: MagicMock
    ) -> None:
        """Time reference resolution should be skipped on failed response."""
        failed_response = MagicMock()
        failed_response.success = False
        failed_response.data = None
        mock_llm_service.generate.return_value = failed_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        # Should not raise even though "recently" is in question
        result = classifier.classify("What happened recently?")

        assert result.success is False


class TestQueryClassifierPromptContent:
    """Test prompt content and structure."""

    def test_prompt_includes_intent_descriptions(
        self, classifier: QueryClassifier, mock_llm_service: MagicMock
    ) -> None:
        """Prompt should describe available intents."""
        classifier.classify("test question")

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]

        assert "event_query" in prompt
        assert "registration_query" in prompt
        assert "contribution_query" in prompt
        assert "out_of_scope" in prompt

    def test_prompt_includes_multi_entity_intents(
        self, classifier: QueryClassifier, mock_llm_service: MagicMock
    ) -> None:
        """Prompt should include multi-entity intent options (T044/US3)."""
        classifier.classify("Who are the speakers at CHEP?")

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]

        # Multi-entity intents should be in prompt
        assert "speaker_query" in prompt
        assert "session_query" in prompt
        assert "attendee_query" in prompt
        assert "schedule_query" in prompt

    def test_prompt_includes_time_reference_guidance(
        self, classifier: QueryClassifier, mock_llm_service: MagicMock
    ) -> None:
        """Prompt should include time reference defaults."""
        classifier.classify("test question")

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]

        assert "recently" in prompt.lower()
        assert "soon" in prompt.lower()
        assert "7 days" in prompt


class TestQueryClassifierTimeReferenceConstants:
    """Test TIME_REFERENCE_DEFAULTS constants."""

    def test_recently_default_is_7(self) -> None:
        """'recently' should default to 7 days."""
        assert QueryClassifier.TIME_REFERENCE_DEFAULTS["recently"] == 7

    def test_soon_default_is_7(self) -> None:
        """'soon' should default to 7 days."""
        assert QueryClassifier.TIME_REFERENCE_DEFAULTS["soon"] == 7

    def test_a_while_ago_default_is_30(self) -> None:
        """'a while ago' should default to 30 days."""
        assert QueryClassifier.TIME_REFERENCE_DEFAULTS["a while ago"] == 30

    def test_this_month_default_is_30(self) -> None:
        """'this month' should default to 30 days."""
        assert QueryClassifier.TIME_REFERENCE_DEFAULTS["this month"] == 30


class TestQueryClassifierMultiEntityIntents:
    """Test multi-entity intent classification (T044/US3)."""

    def test_speaker_query_intent_in_prompt(
        self,
        mock_llm_service: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """speaker_query should be available for speaker questions."""
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        classifier.classify("Who are the speakers at the physics conference?")

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "speaker_query" in prompt
        assert "speaker" in prompt.lower()

    def test_session_query_intent_in_prompt(
        self,
        mock_llm_service: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """session_query should be available for session questions."""
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        classifier.classify("What sessions are in the parallel track?")

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "session_query" in prompt
        assert "session" in prompt.lower()

    def test_attendee_query_intent_in_prompt(
        self,
        mock_llm_service: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """attendee_query should be available for attendee questions."""
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        classifier.classify("Who attended the workshop?")

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "attendee_query" in prompt

    def test_schedule_query_intent_in_prompt(
        self,
        mock_llm_service: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """schedule_query should be available for schedule questions."""
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        classifier.classify("When is the keynote scheduled?")

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "schedule_query" in prompt

    def test_classification_hints_in_prompt(
        self,
        mock_llm_service: MagicMock,
        mock_llm_response: MagicMock,
    ) -> None:
        """Classification hints should guide intent selection."""
        mock_llm_service.generate.return_value = mock_llm_response
        classifier = QueryClassifier(llm_service=mock_llm_service)

        classifier.classify("Who is presenting at the conference?")

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        # Should include hints about when to use which intent
        assert "HINT" in prompt.upper() or "hint" in prompt.lower()
