# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Unit tests for SQLGenerator component."""

from unittest.mock import MagicMock

import pytest

from indico_assistant.services.nl2sql.generator import SQLGenerator


@pytest.fixture
def mock_llm_service() -> MagicMock:
    """Create a mock LLM service."""
    return MagicMock()


@pytest.fixture
def mock_schema_context() -> MagicMock:
    """Create a mock schema context."""
    context = MagicMock()
    context.get_tables_for_intent.return_value = [
        "events.events",
        "events.contributions",
    ]
    context.get_schema_prompt.return_value = """
TABLES:
- events.events: Event table with id, title, start_dt, end_dt
- events.contributions: Contributions table with id, event_id, title
"""
    return context


@pytest.fixture
def mock_classification() -> MagicMock:
    """Create a mock classification."""
    classification = MagicMock()
    classification.intent = "event_query"
    classification.time_range = None
    classification.entities = []
    classification.filters = None
    return classification


@pytest.fixture
def mock_sql_response() -> MagicMock:
    """Create a mock SQL generation response."""
    response = MagicMock()
    response.success = True
    response.data = MagicMock()
    response.data.sql = "SELECT * FROM events.events"
    response.data.parameters = {}
    response.data.explanation = "Query to list events"
    return response


@pytest.fixture
def generator(
    mock_llm_service: MagicMock,
    mock_schema_context: MagicMock,
    mock_sql_response: MagicMock,
) -> SQLGenerator:
    """Create a generator instance."""
    mock_llm_service.generate.return_value = mock_sql_response
    return SQLGenerator(
        llm_service=mock_llm_service,
        schema_context=mock_schema_context,
    )


class TestSQLGeneratorBasicGeneration:
    """Test basic SQL generation functionality."""

    def test_generate_calls_llm(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Should call LLM service to generate SQL."""
        generator.generate("How many events?", mock_classification)

        mock_llm_service.generate.assert_called_once()

    def test_generate_returns_response(
        self,
        generator: SQLGenerator,
        mock_classification: MagicMock,
    ) -> None:
        """Should return LLM response."""
        result = generator.generate("How many events?", mock_classification)

        assert result.success is True
        assert result.data is not None

    def test_generate_uses_correct_response_model(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Should use SQLGeneration response model."""
        generator.generate("List events", mock_classification)

        call_args = mock_llm_service.generate.call_args
        assert "response_model" in call_args[1]


class TestSQLGeneratorPromptConstruction:
    """Test prompt construction with schema context."""

    def test_includes_question_in_prompt(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Question should be included in prompt."""
        question = "How many physics conferences in 2024?"
        generator.generate(question, mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert question in prompt

    def test_includes_intent_in_prompt(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Classification intent should be in prompt."""
        mock_classification.intent = "registration_query"
        generator.generate("List registrations", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "registration_query" in prompt

    def test_includes_schema_context(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Schema context should be included in prompt."""
        generator.generate("List events", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "events.events" in prompt

    def test_gets_tables_for_intent(
        self,
        generator: SQLGenerator,
        mock_schema_context: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Should get tables based on classification intent."""
        mock_classification.intent = "contribution_query"
        generator.generate("List speakers", mock_classification)

        mock_schema_context.get_tables_for_intent.assert_called_with(
            "contribution_query"
        )

    def test_includes_time_range_in_prompt(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Time range should be formatted and included."""
        mock_time_range = MagicMock()
        mock_time_range.start = "2024-01-01"
        mock_time_range.end = "2024-12-31"
        mock_classification.time_range = mock_time_range

        generator.generate("Events in 2024", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "2024-01-01" in prompt
        assert "2024-12-31" in prompt

    def test_includes_entities_in_prompt(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Classification entities should be in prompt."""
        entity = MagicMock()
        entity.type = "event_name"
        entity.value = "Physics Conference"
        mock_classification.entities = [entity]

        generator.generate("Events like Physics Conference", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "event_name" in prompt
        assert "Physics Conference" in prompt


class TestSQLGeneratorPermissionFilter:
    """Test permission filter injection (FR-007, FR-008)."""

    def test_no_filter_when_no_event_ids(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """No permission filter when allowed_event_ids is None."""
        generator.generate("List events", mock_classification, allowed_event_ids=None)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "PERMISSION FILTER" not in prompt

    def test_empty_result_message_for_no_access(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Empty event list should indicate no access."""
        generator.generate("List events", mock_classification, allowed_event_ids=[])

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "no accessible events" in prompt.lower()

    def test_includes_event_ids_in_filter(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Event IDs should be included in permission filter."""
        event_ids = [1, 2, 3, 4, 5]
        generator.generate(
            "List events", mock_classification, allowed_event_ids=event_ids
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "PERMISSION FILTER" in prompt
        for event_id in event_ids:
            assert str(event_id) in prompt

    def test_truncates_large_event_id_list(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Large event ID lists should be truncated in display."""
        event_ids = list(range(1, 101))  # 100 events
        generator.generate(
            "List events", mock_classification, allowed_event_ids=event_ids
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "PERMISSION FILTER" in prompt

    def test_very_large_list_uses_parameter_reference(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Very large event ID lists should reference parameter."""
        event_ids = list(range(1, 201))  # 200 events
        generator.generate(
            "List events", mock_classification, allowed_event_ids=event_ids
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        # Should mention using a parameter for large lists
        assert "allowed_event_ids" in prompt or "event_id IN" in prompt


class TestSQLGeneratorPromptRules:
    """Test that prompt includes safety rules."""

    def test_prompt_includes_select_only_rule(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Prompt should enforce SELECT-only."""
        generator.generate("List events", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "SELECT" in prompt
        assert "never INSERT" in prompt.lower() or "only generate select" in prompt.lower()

    def test_prompt_forbids_cte(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Prompt should forbid CTEs."""
        generator.generate("List events", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "CTE" in prompt.upper() or "WITH" in prompt

    def test_prompt_forbids_subqueries(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Prompt should forbid subqueries."""
        generator.generate("List events", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "subquer" in prompt.lower()

    def test_prompt_forbids_window_functions(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Prompt should forbid window functions."""
        generator.generate("List events", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "window function" in prompt.lower()


class TestSQLGeneratorSchemaContextAccess:
    """Test schema context access."""

    def test_schema_context_property(
        self, mock_llm_service: MagicMock, mock_schema_context: MagicMock
    ) -> None:
        """Should expose schema context via property."""
        generator = SQLGenerator(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
        )

        assert generator.schema_context is mock_schema_context


class TestSQLGeneratorFailedResponse:
    """Test handling of failed LLM responses."""

    def test_returns_failed_response(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Failed LLM response should be returned."""
        failed_response = MagicMock()
        failed_response.success = False
        failed_response.data = None
        failed_response.error = "Generation failed"
        mock_llm_service.generate.return_value = failed_response

        generator = SQLGenerator(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
        )

        result = generator.generate("List events", mock_classification)

        assert result.success is False
        assert result.error == "Generation failed"


class TestSQLGeneratorFiltersHandling:
    """Test handling of classification filters."""

    def test_includes_filters_in_prompt(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Classification filters should be included in prompt."""
        mock_classification.filters = {"category": "physics", "year": 2024}

        generator.generate("Physics events in 2024", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "physics" in prompt.lower() or "category" in prompt.lower()

    def test_none_filters_handled(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """None filters should be handled gracefully."""
        mock_classification.filters = None

        # Should not raise
        generator.generate("List events", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "None" in prompt or "Filters" in prompt


class TestSQLGeneratorTimeRangeFormatting:
    """Test time range formatting in prompts."""

    def test_no_time_range_shows_none(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """No time range should show 'None' in prompt."""
        mock_classification.time_range = None

        generator.generate("List all events", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        # Time range should be marked as None
        assert "Time Range: None" in prompt or "time_range" in prompt.lower()

    def test_time_range_formatted_with_from_to(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Time range should be formatted with From/To."""
        mock_time_range = MagicMock()
        mock_time_range.start = "2024-06-01"
        mock_time_range.end = "2024-06-30"
        mock_classification.time_range = mock_time_range

        generator.generate("Events in June", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "From" in prompt
        assert "2024-06-01" in prompt
        assert "2024-06-30" in prompt


class TestSQLGeneratorEntityFormatting:
    """Test entity formatting in prompts."""

    def test_no_entities_shows_none(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """No entities should show 'None' in prompt."""
        mock_classification.entities = []

        generator.generate("List events", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "None" in prompt

    def test_multiple_entities_formatted(
        self,
        generator: SQLGenerator,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Multiple entities should be comma-separated."""
        entity1 = MagicMock()
        entity1.type = "event_name"
        entity1.value = "CHEP"
        entity2 = MagicMock()
        entity2.type = "person_name"
        entity2.value = "John Doe"
        mock_classification.entities = [entity1, entity2]

        generator.generate("CHEP talks by John Doe", mock_classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "event_name" in prompt
        assert "CHEP" in prompt
        assert "person_name" in prompt
        assert "John Doe" in prompt


class TestSQLGeneratorMultiEntitySupport:
    """Test multi-entity query support (T045/US3)."""

    def test_is_multi_entity_intent_speaker_query(
        self, generator: SQLGenerator
    ) -> None:
        """speaker_query should be identified as multi-entity."""
        assert generator.is_multi_entity_intent("speaker_query") is True

    def test_is_multi_entity_intent_session_query(
        self, generator: SQLGenerator
    ) -> None:
        """session_query should be identified as multi-entity."""
        assert generator.is_multi_entity_intent("session_query") is True

    def test_is_multi_entity_intent_attendee_query(
        self, generator: SQLGenerator
    ) -> None:
        """attendee_query should be identified as multi-entity."""
        assert generator.is_multi_entity_intent("attendee_query") is True

    def test_is_multi_entity_intent_schedule_query(
        self, generator: SQLGenerator
    ) -> None:
        """schedule_query should be identified as multi-entity."""
        assert generator.is_multi_entity_intent("schedule_query") is True

    def test_is_multi_entity_intent_contribution_query(
        self, generator: SQLGenerator
    ) -> None:
        """contribution_query should be identified as multi-entity."""
        assert generator.is_multi_entity_intent("contribution_query") is True

    def test_is_not_multi_entity_intent_event_list(
        self, generator: SQLGenerator
    ) -> None:
        """event_list should NOT be identified as multi-entity."""
        assert generator.is_multi_entity_intent("event_list") is False

    def test_is_not_multi_entity_intent_registration_query(
        self, generator: SQLGenerator
    ) -> None:
        """registration_query should NOT be identified as multi-entity."""
        assert generator.is_multi_entity_intent("registration_query") is False

    def test_multi_entity_intents_constant_exists(
        self, generator: SQLGenerator
    ) -> None:
        """MULTI_ENTITY_INTENTS constant should exist."""
        assert hasattr(SQLGenerator, "MULTI_ENTITY_INTENTS")
        assert isinstance(SQLGenerator.MULTI_ENTITY_INTENTS, (set, frozenset))

    def test_multi_entity_intents_contains_expected(self) -> None:
        """MULTI_ENTITY_INTENTS should contain all expected intents."""
        expected = {
            "contribution_query",
            "speaker_query",
            "session_query",
            "attendee_query",
            "schedule_query",
        }
        assert expected.issubset(SQLGenerator.MULTI_ENTITY_INTENTS)


class TestSQLGeneratorJoinHintsIntegration:
    """Test JOIN hints integration in prompts (T045/US3)."""

    def test_multi_entity_intent_includes_join_hints(
        self,
        mock_llm_service: MagicMock,
        mock_llm_response: MagicMock,
        mock_schema_context: MagicMock,
    ) -> None:
        """Multi-entity intents should include JOIN hints in prompt."""
        mock_llm_service.generate.return_value = mock_llm_response
        mock_schema_context.get_schema_prompt_with_joins.return_value = (
            "SCHEMA WITH JOINS"
        )
        mock_schema_context.get_schema_prompt.return_value = "PLAIN SCHEMA"

        generator = SQLGenerator(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
        )

        classification = MagicMock()
        classification.intent = "speaker_query"  # Multi-entity intent
        classification.filters = {}
        classification.time_range = None
        classification.entities = []

        generator.generate("Who are the speakers?", classification)

        # Should use schema with joins
        mock_schema_context.get_schema_prompt_with_joins.assert_called_once()

    def test_single_entity_intent_uses_plain_schema(
        self,
        mock_llm_service: MagicMock,
        mock_llm_response: MagicMock,
        mock_schema_context: MagicMock,
    ) -> None:
        """Single-entity intents should use plain schema prompt."""
        mock_llm_service.generate.return_value = mock_llm_response
        mock_schema_context.get_schema_prompt_with_joins.return_value = (
            "SCHEMA WITH JOINS"
        )
        mock_schema_context.get_schema_prompt.return_value = "PLAIN SCHEMA"

        generator = SQLGenerator(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
        )

        classification = MagicMock()
        classification.intent = "event_list"  # Single-entity intent
        classification.filters = {}
        classification.time_range = None
        classification.entities = []

        generator.generate("List all events", classification)

        # Should use plain schema (not with joins)
        mock_schema_context.get_schema_prompt.assert_called_once()
        mock_schema_context.get_schema_prompt_with_joins.assert_not_called()

    def test_join_hint_prompt_includes_left_join_guidance(
        self,
        mock_llm_service: MagicMock,
        mock_llm_response: MagicMock,
        mock_schema_context: MagicMock,
    ) -> None:
        """JOIN hints prompt should include LEFT JOIN guidance."""
        mock_llm_service.generate.return_value = mock_llm_response
        join_schema = """
        TABLE: events
        JOIN HINTS:
        - Use LEFT JOIN for contributions: e.id = c.event_id
        """
        mock_schema_context.get_schema_prompt_with_joins.return_value = join_schema
        mock_schema_context.get_schema_prompt.return_value = "PLAIN SCHEMA"

        generator = SQLGenerator(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
        )

        classification = MagicMock()
        classification.intent = "speaker_query"
        classification.filters = {}
        classification.time_range = None
        classification.entities = []

        generator.generate("Who is presenting?", classification)

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "JOIN" in prompt.upper()
