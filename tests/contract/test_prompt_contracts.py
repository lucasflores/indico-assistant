"""Contract tests for NL2SQL prompt outputs."""

import pytest

from indico_assistant.services.nl2sql.generator import SQL_GENERATION_PROMPT
from indico_assistant.services.nl2sql.classifier import CLASSIFICATION_PROMPT
from indico_assistant.services.nl2sql.schema import SchemaContext
from indico_assistant.services.nl2sql.validator import SQLValidator


@pytest.mark.contract
def test_event_query_required_columns_in_prompt() -> None:
    """Prompt includes required event output columns."""
    required = [
        "event_id",
        "event_title",
        "event_start_dt",
        "event_timezone",
    ]
    for token in required:
        assert token in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_date_formatting_in_prompt() -> None:
    """Prompt includes timezone-aware date formatting guidance."""
    assert "to_char" in SQL_GENERATION_PROMPT
    assert "AT TIME ZONE" in SQL_GENERATION_PROMPT
    # (issue #4: start_dt is UTC without a zone; converting it straight to the event's zone read it as local)
    assert "(e.start_dt AT TIME ZONE 'UTC') AT TIME ZONE e.timezone" in SQL_GENERATION_PROMPT
    assert "to_char(e.start_dt AT TIME ZONE e.timezone" not in SQL_GENERATION_PROMPT
    # a day is the event's local day, all of it ("on October 2" became BETWEEN '2026-10-02' AND '2026-10-02')
    assert "AT TIME ZONE e.timezone)::date BETWEEN '{{START_DATE}}' AND '{{END_DATE}}'" in SQL_GENERATION_PROMPT
    assert "e.start_dt BETWEEN '{{START_DATE}}'" not in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_date_comparison_functions_in_prompt() -> None:
    """Prompt instructs using PostgreSQL date functions for current date."""
    assert "CURRENT_DATE" in SQL_GENERATION_PROMPT
    assert "NOW()" in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_forbidden_patterns_are_explicitly_blocked() -> None:
    """Prompt explicitly blocks CTEs, subqueries, and window functions."""
    assert "Do NOT use CTEs" in SQL_GENERATION_PROMPT
    assert "subqueries" in SQL_GENERATION_PROMPT
    assert "window functions" in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_speaker_query_uses_string_agg() -> None:
    """Prompt includes STRING_AGG pattern for speaker aggregation."""
    assert "STRING_AGG" in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_speaker_query_includes_join_tables() -> None:
    """Prompt includes contribution/person join tables in template."""
    assert "events.contribution_person_links" in SQL_GENERATION_PROMPT
    assert "events.persons" in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_speaker_query_includes_group_by() -> None:
    """Prompt includes GROUP BY for aggregation queries."""
    assert "GROUP BY" in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_document_query_vector_pattern_in_prompt() -> None:
    """Prompt includes vector search pattern in the document template."""
    assert "plugin_assistant.extracted_documents" in SQL_GENERATION_PROMPT
    assert "<=> :query_vector" in SQL_GENERATION_PROMPT
    assert "ORDER BY" in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_classification_includes_document_content_intent() -> None:
    """Classifier prompt includes document_content_query intent."""
    assert "document_content_query" in CLASSIFICATION_PROMPT


@pytest.mark.contract
def test_classification_includes_attachment_metadata_rule() -> None:
    """Classifier prompt distinguishes attachment metadata queries."""
    assert "attachment_query" in CLASSIFICATION_PROMPT
    assert "FILE METADATA" in CLASSIFICATION_PROMPT


@pytest.mark.contract
def test_classification_includes_hybrid_rule() -> None:
    """Classifier prompt documents hybrid query routing behavior."""
    assert "Hybrid Queries" in CLASSIFICATION_PROMPT


@pytest.mark.contract
def test_attachment_query_includes_folder_attachment_file_joins() -> None:
    """Prompt includes attachment folder/file join pattern."""
    assert "attachments.folders" in SQL_GENERATION_PROMPT
    assert "attachments.attachments" in SQL_GENERATION_PROMPT
    assert "attachments.files" in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_prompt_includes_alternative_patterns() -> None:
    """Prompt documents alternative patterns for restricted syntax."""
    assert "ALTERNATIVE PATTERNS" in SQL_GENERATION_PROMPT
    assert "ORDER BY + LIMIT" in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_prompt_includes_text_matching_rules() -> None:
    """Prompt includes ILIKE guidance for partial matches."""
    assert "TEXT MATCHING RULES" in SQL_GENERATION_PROMPT
    assert "ILIKE" in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_prompt_includes_current_user_filtering() -> None:
    """Prompt documents current user filtering with :user_id."""
    assert "CURRENT USER FILTERING" in SQL_GENERATION_PROMPT
    assert ":user_id" in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_prompt_has_a_context_section() -> None:
    """Today, the user and the event are filled in per question (test_generator checks the lines)."""
    assert "{context_section}" in SQL_GENERATION_PROMPT
    assert "EVENT CONTEXT" in SQL_GENERATION_PROMPT


@pytest.mark.contract
def test_validator_messages_suggest_alternatives() -> None:
    """Validator errors suggest JOINs or ORDER BY + LIMIT."""
    validator = SQLValidator(SchemaContext())
    cte_result = validator.validate("WITH t AS (SELECT 1) SELECT * FROM t")
    assert any("JOINs instead" in v for v in cte_result.violations)

    window_result = validator.validate("SELECT 1 OVER (PARTITION BY 1)")
    assert any("ORDER BY + LIMIT" in v for v in window_result.violations)
