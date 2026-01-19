# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Schema context provider for NL2SQL pipeline.

Manages database schema information and provides relevant schema context
to the LLM for SQL generation. Supports intent-to-tables mapping for
efficient context loading.
"""

from pathlib import Path
from typing import Any

import yaml


class SchemaContext:
    """Manages database schema context for LLM prompts."""

    # Intent-to-tables mapping (FR-002: relevant tables only)
    # Extended for multi-entity queries (US3)
    INTENT_TABLES_MAP: dict[str, list[str]] = {
        # Basic queries - single table focus
        "event_query": [
            "events.events",
            "categories.categories",
        ],
        "registration_query": [
            "events.events",
            "events.registrations",
            "events.registration_data",
        ],
        # Multi-entity queries - multiple table JOINs (US3)
        "contribution_query": [
            "events.events",
            "events.contributions",
            "events.persons",
            "events.contribution_person_links",
            "events.sessions",
        ],
        "speaker_query": [
            "events.events",
            "events.contributions",
            "events.persons",
            "events.contribution_person_links",
        ],
        "session_query": [
            "events.events",
            "events.sessions",
            "events.contributions",
            "events.session_blocks",
        ],
        "attendee_query": [
            "events.events",
            "events.registrations",
            "events.persons",
        ],
        "attachment_query": [
            "attachments.files",
            "attachments.folders",
            "events.events",
            "events.contributions",
            "plugin_assistant.extracted_documents",
        ],
        "schedule_query": [
            "events.events",
            "events.timetable_entries",
            "events.contributions",
            "events.sessions",
            "events.session_blocks",
        ],
        # Fallback for general queries
        "general_info": ["events.events"],
        "out_of_scope": [],
    }

    # JOIN hints for multi-table queries (T042)
    TABLE_JOIN_HINTS: dict[str, dict[str, str]] = {
        "events.events": {
            "events.contributions": "e.id = c.event_id",
            "events.registrations": "e.id = r.event_id",
            "events.sessions": "e.id = s.event_id",
            "events.timetable_entries": "e.id = te.event_id",
            "categories.categories": "e.category_id = cat.id",
        },
        "events.contributions": {
            "events.contribution_person_links": "c.id = cpl.contribution_id",
            "events.sessions": "c.session_id = s.id",
        },
        "events.contribution_person_links": {
            "events.persons": "cpl.person_id = p.id",
        },
        "events.sessions": {
            "events.session_blocks": "s.id = sb.session_id",
            "events.timetable_entries": "s.id = te.session_id",
        },
    }

    def __init__(self, schema_file_path: str | None = None) -> None:
        """
        Initialize schema context.

        Args:
            schema_file_path: Path to YAML file containing schema definitions.
                If None, uses default path from config.
        """
        self._schema_file_path = schema_file_path
        self._schema_cache: dict[str, Any] | None = None

    def _load_schema(self) -> dict[str, Any]:
        """Load schema from YAML file."""
        if self._schema_cache is not None:
            return self._schema_cache

        if self._schema_file_path is None:
            # Prefer curated schema file if present, then fall back to full schema
            base_path = Path(__file__).parent.parent.parent / "config_modules"
            curated_path = base_path / "available_tables.yaml"
            default_path = base_path / "all_tables.yaml"
            if curated_path.exists():
                self._schema_file_path = str(curated_path)
            else:
                self._schema_file_path = str(default_path)

        path = Path(self._schema_file_path)
        if not path.exists():
            # Fallback: attempt to build minimal schema from database
            self._schema_cache = self._build_schema_from_database()
            return self._schema_cache

        with open(path, "r") as f:
            self._schema_cache = yaml.safe_load(f) or {}

        # Ensure all intent tables are represented; fill missing from DB
        missing_tables = []
        for intent_tables in self.INTENT_TABLES_MAP.values():
            for table_name in intent_tables:
                if table_name not in self._schema_cache:
                    missing_tables.append(table_name)

        if missing_tables:
            db_schema = self._build_schema_from_database()
            for table_name in missing_tables:
                if table_name in db_schema:
                    self._schema_cache[table_name] = db_schema[table_name]

        return self._schema_cache

    def _build_schema_from_database(self) -> dict[str, Any]:
        """Build a minimal schema from the live database if YAML is missing.

        Returns:
            Dictionary in the same shape as the YAML schema.
        """
        try:
            from indico.core.db import db
            from sqlalchemy import inspect
        except Exception:
            return {}

        try:
            engine = db.session.get_bind()
            inspector = inspect(engine)
        except Exception:
            return {}

        schema: dict[str, Any] = {}

        # Build list of tables referenced by intents
        tables = set()
        for intent_tables in self.INTENT_TABLES_MAP.values():
            tables.update(intent_tables)

        for table_ref in sorted(tables):
            if "." in table_ref:
                schema_name, table_name = table_ref.split(".", 1)
            else:
                schema_name, table_name = None, table_ref

            try:
                columns = inspector.get_columns(table_name, schema=schema_name)
            except Exception:
                continue

            column_map: dict[str, Any] = {}
            for col in columns:
                col_type = str(col.get("type", "unknown"))
                column_map[col["name"]] = {
                    "type": col_type,
                    "description": "",
                    "nullable": bool(col.get("nullable", True)),
                }

            schema[table_ref] = {
                "description": "",
                "columns": column_map,
                "relationships": [],
            }

        return schema

    def get_tables_for_intent(self, intent: str) -> list[str]:
        """
        Get list of relevant tables for a given query intent.

        Args:
            intent: The classified query intent (e.g., 'event_query')

        Returns:
            List of table names relevant to the intent.
        """
        return self.INTENT_TABLES_MAP.get(intent, ["events.events"])

    def get_schema_prompt(self, tables: list[str]) -> str:
        """
        Generate schema prompt text for the specified tables.

        Args:
            tables: List of table names to include in the prompt

        Returns:
            Formatted schema information as a string for the LLM prompt.
        """
        schema = self._load_schema()
        prompt_parts = ["## Database Schema\n"]

        for table_name in tables:
            if table_name in schema:
                table_info = schema[table_name]
                prompt_parts.append(f"### Table: {table_name}\n")

                if "description" in table_info:
                    prompt_parts.append(f"{table_info['description']}\n")

                if "columns" in table_info:
                    prompt_parts.append("Columns:\n")
                    for col_name, col_info in table_info["columns"].items():
                        col_type = col_info.get("type", "unknown")
                        col_desc = col_info.get("description", "")
                        nullable = col_info.get("nullable", True)
                        null_str = "" if nullable else " NOT NULL"
                        prompt_parts.append(
                            f"  - {col_name} ({col_type}{null_str}): {col_desc}\n"
                        )

                if "relationships" in table_info:
                    prompt_parts.append("Relationships:\n")
                    for rel in table_info["relationships"]:
                        prompt_parts.append(f"  - {rel}\n")

                prompt_parts.append("\n")

        if len(prompt_parts) == 1:
            # No schema found, provide minimal context
            prompt_parts.append(
                "Note: Detailed schema not available. "
                "Use standard SQL SELECT syntax.\n"
            )

        return "".join(prompt_parts)

    def get_all_allowed_tables(
        self, allowlist: list[str] | None = None
    ) -> list[str]:
        """
        Get all tables that are allowed for queries.

        Args:
            allowlist: Optional explicit list of allowed tables.
                If None, returns all tables in schema.

        Returns:
            List of allowed table names.
        """
        if allowlist is not None:
            return allowlist

        schema = self._load_schema()
        return list(schema.keys())

    def is_table_allowed(
        self, table_name: str, allowlist: list[str] | None = None
    ) -> bool:
        """
        Check if a table is in the allowlist.

        Args:
            table_name: Name of the table to check
            allowlist: Optional explicit list of allowed tables

        Returns:
            True if the table is allowed.
        """
        allowed = self.get_all_allowed_tables(allowlist)
        return table_name in allowed

    def get_join_hints(self, tables: list[str]) -> str:
        """
        Generate JOIN hints for multi-table queries (T042).

        Args:
            tables: List of tables that will be used in the query

        Returns:
            Formatted JOIN hints as a string for the LLM prompt.
        """
        if len(tables) < 2:
            return ""

        hints = ["## JOIN Hints\n"]
        hints.append("Use these JOIN conditions when combining tables:\n\n")

        for base_table in tables:
            if base_table in self.TABLE_JOIN_HINTS:
                related_joins = self.TABLE_JOIN_HINTS[base_table]
                for target_table, condition in related_joins.items():
                    if target_table in tables:
                        base_alias = self._get_suggested_alias(base_table)
                        target_alias = self._get_suggested_alias(target_table)
                        hints.append(
                            f"- {base_table} ({base_alias}) JOIN "
                            f"{target_table} ({target_alias}): ON {condition}\n"
                        )

        if len(hints) == 2:
            # No relevant joins found
            return ""

        hints.append("\n")
        return "".join(hints)

    def _get_suggested_alias(self, table_name: str) -> str:
        """
        Get a suggested table alias for SQL queries.

        Args:
            table_name: Full table name (e.g., 'events.contributions')

        Returns:
            Short alias (e.g., 'c')
        """
        alias_map = {
            "events.events": "e",
            "events.contributions": "c",
            "events.persons": "p",
            "events.registrations": "r",
            "events.sessions": "s",
            "events.session_blocks": "sb",
            "events.contribution_person_links": "cpl",
            "events.timetable_entries": "te",
            "events.registration_data": "rd",
            "categories.categories": "cat",
            "attachments.files": "f",
            "attachments.folders": "fo",
        }
        return alias_map.get(table_name, table_name.split(".")[-1][0])

    def get_schema_prompt_with_joins(self, tables: list[str]) -> str:
        """
        Generate complete schema prompt including JOIN hints (US3).

        This combines the regular schema prompt with JOIN hints
        for multi-entity queries.

        Args:
            tables: List of table names to include

        Returns:
            Combined schema and JOIN hints string.
        """
        schema_prompt = self.get_schema_prompt(tables)
        join_hints = self.get_join_hints(tables)
        return schema_prompt + join_hints
