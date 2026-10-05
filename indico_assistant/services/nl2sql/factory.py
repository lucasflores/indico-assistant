# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Factory functions for NL2SQL pipeline creation.

Provides convenient factory functions to create configured pipeline
instances with appropriate defaults.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from indico_assistant.services.llm import LLMService
from indico_assistant.services.nl2sql.cache import QueryCache
from indico_assistant.services.nl2sql.pipeline import NL2SQLPipeline
from indico_assistant.services.nl2sql.schema import SchemaContext


if TYPE_CHECKING:
    from indico_assistant.plugin import AssistantPlugin


def create_nl2sql_pipeline(
    llm_service: LLMService,
    schema_file_path: str | None = None,
    db_session_factory: Callable[[], Any] | None = None,
    enable_cache: bool = False,
    cache_ttl_seconds: int = 600,
    cache_max_entries: int = 1000,
    max_rows: int = 1000,
    timeout_seconds: int = 10,
    max_correction_attempts: int = 3,
    allowed_tables: list[str] | None = None,
    connection_factory: Callable[[], Any] | None = None,
    audit_enabled: bool = True,
) -> NL2SQLPipeline:
    """
    Create and configure an NL2SQL pipeline instance.

    This factory function creates a fully configured pipeline with
    sensible defaults. It handles:
    - Schema context loading
    - Cache configuration
    - Database session management

    Args:
        llm_service: Pre-configured LLM service (required).
        schema_file_path: Path to schema YAML file.
            If None, uses default path.
        db_session_factory: Session factory for the audit log (never runs generated SQL).
            If None, uses Indico's db.session.
        enable_cache: Whether to enable query caching (default: False). Its key (user, SQL) ignores the
            event scope of the question, so only enable it for callers with a single scope.
        cache_ttl_seconds: Cache TTL in seconds (default: 600).
        cache_max_entries: Maximum cache entries (default: 1000).
        max_rows: Maximum rows to return (default: 1000).
        timeout_seconds: Query timeout (default: 10).
        max_correction_attempts: Max error corrections (default: 3).
        allowed_tables: Optional explicit table allowlist.
        connection_factory: Connections for generated SQL (default: the read-only NL2SQL role).
        audit_enabled: Whether to write the query audit log (default: True).

    Returns:
        Configured NL2SQLPipeline instance.
    """
    # Create schema context
    schema_context = SchemaContext(schema_file_path)

    # Get or create db session factory
    if db_session_factory is None:
        from indico.core.db import db

        def default_session_factory() -> Any:
            return db.session

        db_session_factory = default_session_factory

    # Create cache if enabled
    cache = None
    if enable_cache:
        cache = QueryCache(
            ttl_seconds=cache_ttl_seconds,
            max_entries=cache_max_entries,
        )

    return NL2SQLPipeline(
        llm_service=llm_service,
        schema_context=schema_context,
        db_session_factory=db_session_factory,
        connection_factory=connection_factory,
        cache=cache,
        max_rows=max_rows,
        timeout_seconds=timeout_seconds,
        max_correction_attempts=max_correction_attempts,
        allowed_tables=allowed_tables,
        audit_enabled=audit_enabled,
    )


def create_nl2sql_pipeline_from_plugin(
    plugin: "AssistantPlugin",
) -> NL2SQLPipeline:
    """
    Create an NL2SQL pipeline from plugin settings.

    Reads all configuration from the Indico plugin settings:
    - nl2sql_timeout
    - nl2sql_max_rows
    - nl2sql_max_corrections
    - nl2sql_allowed_tables

    Args:
        plugin: The AssistantPlugin instance.

    Returns:
        Configured NL2SQLPipeline instance.
    """
    llm_service = plugin.llm_service  # one per process: keeps the HTTP connection pool across chats

    # Read settings with defaults
    settings = plugin.settings
    timeout = settings.get("nl2sql_timeout", 10)
    max_rows = settings.get("nl2sql_max_rows", 1000)
    max_corrections = settings.get("nl2sql_max_corrections", 3)
    allowed_tables = settings.get("nl2sql_allowed_tables")

    return create_nl2sql_pipeline(
        llm_service=llm_service,
        # ponytail: no result cache (see enable_cache); a shared one would need the full QueryContext in the key
        enable_cache=False,
        max_rows=max_rows,
        timeout_seconds=timeout,
        max_correction_attempts=max_corrections,
        allowed_tables=allowed_tables,
    )
