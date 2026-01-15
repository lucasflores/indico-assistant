# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Unit tests for SchemaContext class.

Tests the schema context provider that manages database schema information
for LLM prompts.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from indico_assistant.services.nl2sql.schema import SchemaContext


class TestSchemaContextIntentMapping:
    """Tests for intent-to-tables mapping."""

    def test_event_query_intent_returns_event_tables(self):
        """Event query intent should return events and categories tables."""
        context = SchemaContext()
        tables = context.get_tables_for_intent("event_query")
        
        assert "events.events" in tables
        assert "categories.categories" in tables

    def test_registration_query_intent_returns_registration_tables(self):
        """Registration query intent should return events and registrations tables."""
        context = SchemaContext()
        tables = context.get_tables_for_intent("registration_query")
        
        assert "events.events" in tables
        assert "events.registrations" in tables

    def test_contribution_query_intent_returns_contribution_tables(self):
        """Contribution query intent should return contribution-related tables."""
        context = SchemaContext()
        tables = context.get_tables_for_intent("contribution_query")
        
        assert "events.events" in tables
        assert "events.contributions" in tables
        assert "events.persons" in tables
        assert "events.contribution_person_links" in tables

    def test_attachment_query_intent_returns_attachment_tables(self):
        """Attachment query intent should return files and events tables."""
        context = SchemaContext()
        tables = context.get_tables_for_intent("attachment_query")
        
        assert "attachments.files" in tables
        assert "events.events" in tables

    def test_general_info_intent_returns_events_table(self):
        """General info intent should return events table."""
        context = SchemaContext()
        tables = context.get_tables_for_intent("general_info")
        
        assert "events.events" in tables

    def test_unknown_intent_returns_default_events_table(self):
        """Unknown intent should default to events table."""
        context = SchemaContext()
        tables = context.get_tables_for_intent("unknown_intent")
        
        assert tables == ["events.events"]


class TestSchemaContextSchemaLoading:
    """Tests for schema loading from YAML."""

    def test_load_schema_from_file(self):
        """Should load schema from a YAML file."""
        schema_content = {
            "events.events": {
                "description": "Core events table",
                "columns": {
                    "id": {"type": "integer", "nullable": False, "description": "Primary key"},
                    "title": {"type": "varchar", "nullable": False, "description": "Event title"},
                },
                "relationships": ["categories via category_id"],
            }
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(schema_content, f)
            schema_file = f.name
        
        try:
            context = SchemaContext(schema_file)
            prompt = context.get_schema_prompt(["events.events"])
            
            assert "events.events" in prompt
            assert "Core events table" in prompt
            assert "id (integer NOT NULL)" in prompt
            assert "title (varchar NOT NULL)" in prompt
        finally:
            Path(schema_file).unlink()

    def test_schema_caching(self):
        """Schema should be cached after first load."""
        schema_content = {"test.table": {"description": "Test table"}}
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(schema_content, f)
            schema_file = f.name
        
        try:
            context = SchemaContext(schema_file)
            
            # First load
            context.get_schema_prompt(["test.table"])
            
            # Delete file - should still work due to caching
            Path(schema_file).unlink()
            
            # Second load should use cache
            prompt = context.get_schema_prompt(["test.table"])
            assert "Test table" in prompt
        except Exception:
            # Clean up if test fails before deletion
            if Path(schema_file).exists():
                Path(schema_file).unlink()
            raise

    def test_missing_schema_file_returns_empty_schema(self):
        """Missing schema file should return empty schema with fallback message."""
        context = SchemaContext("/nonexistent/path/schema.yaml")
        prompt = context.get_schema_prompt(["any.table"])
        
        assert "Note: Detailed schema not available" in prompt

    def test_missing_table_in_schema(self):
        """Missing table in schema should not appear in prompt."""
        schema_content = {"events.events": {"description": "Events table"}}
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(schema_content, f)
            schema_file = f.name
        
        try:
            context = SchemaContext(schema_file)
            prompt = context.get_schema_prompt(["nonexistent.table"])
            
            # Should have fallback message since no tables were found
            assert "Note: Detailed schema not available" in prompt
        finally:
            Path(schema_file).unlink()


class TestSchemaContextAllowedTables:
    """Tests for table allowlist functionality."""

    def test_get_all_allowed_tables_with_explicit_list(self):
        """Should return explicit allowlist when provided."""
        context = SchemaContext()
        allowlist = ["events.events", "events.registrations"]
        
        allowed = context.get_all_allowed_tables(allowlist)
        
        assert allowed == allowlist

    def test_get_all_allowed_tables_without_list_returns_schema_tables(self):
        """Without explicit list, should return all tables from schema."""
        schema_content = {
            "events.events": {"description": "Events"},
            "events.registrations": {"description": "Registrations"},
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(schema_content, f)
            schema_file = f.name
        
        try:
            context = SchemaContext(schema_file)
            allowed = context.get_all_allowed_tables()
            
            assert "events.events" in allowed
            assert "events.registrations" in allowed
        finally:
            Path(schema_file).unlink()

    def test_is_table_allowed_with_explicit_list(self):
        """Should check if table is in explicit allowlist."""
        context = SchemaContext()
        allowlist = ["events.events", "events.registrations"]
        
        assert context.is_table_allowed("events.events", allowlist) is True
        assert context.is_table_allowed("events.registrations", allowlist) is True
        assert context.is_table_allowed("events.contributions", allowlist) is False

    def test_is_table_allowed_without_list_checks_schema(self):
        """Without explicit list, should check against schema tables."""
        schema_content = {"events.events": {"description": "Events"}}
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(schema_content, f)
            schema_file = f.name
        
        try:
            context = SchemaContext(schema_file)
            
            assert context.is_table_allowed("events.events") is True
            assert context.is_table_allowed("nonexistent.table") is False
        finally:
            Path(schema_file).unlink()


class TestSchemaContextSchemaPrompt:
    """Tests for schema prompt generation."""

    def test_schema_prompt_includes_all_requested_tables(self):
        """Schema prompt should include all requested tables."""
        schema_content = {
            "events.events": {"description": "Events table"},
            "events.registrations": {"description": "Registrations table"},
            "events.contributions": {"description": "Contributions table"},
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(schema_content, f)
            schema_file = f.name
        
        try:
            context = SchemaContext(schema_file)
            prompt = context.get_schema_prompt([
                "events.events",
                "events.registrations",
            ])
            
            assert "events.events" in prompt
            assert "Events table" in prompt
            assert "events.registrations" in prompt
            assert "Registrations table" in prompt
            # Should not include unrequested table
            assert "Contributions table" not in prompt
        finally:
            Path(schema_file).unlink()

    def test_schema_prompt_includes_column_details(self):
        """Schema prompt should include column types and descriptions."""
        schema_content = {
            "events.events": {
                "columns": {
                    "id": {
                        "type": "integer",
                        "nullable": False,
                        "description": "Primary key",
                    },
                    "title": {
                        "type": "varchar(255)",
                        "nullable": True,
                        "description": "Event title",
                    },
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(schema_content, f)
            schema_file = f.name
        
        try:
            context = SchemaContext(schema_file)
            prompt = context.get_schema_prompt(["events.events"])
            
            assert "id (integer NOT NULL)" in prompt
            assert "Primary key" in prompt
            assert "title (varchar(255))" in prompt
            assert "Event title" in prompt
        finally:
            Path(schema_file).unlink()

    def test_schema_prompt_includes_relationships(self):
        """Schema prompt should include table relationships."""
        schema_content = {
            "events.events": {
                "relationships": [
                    "categories via category_id",
                    "registrations via event_id",
                ]
            }
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(schema_content, f)
            schema_file = f.name
        
        try:
            context = SchemaContext(schema_file)
            prompt = context.get_schema_prompt(["events.events"])
            
            assert "Relationships:" in prompt
            assert "categories via category_id" in prompt
            assert "registrations via event_id" in prompt
        finally:
            Path(schema_file).unlink()
