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
from indico_assistant.services.embedding.service import (
    EmbeddingService,
    create_embedding_service,
)
from indico_assistant.services.nl2sql.cache import QueryCache
from indico_assistant.services.nl2sql.pipeline import NL2SQLPipeline
from indico_assistant.services.nl2sql.schema import SchemaContext


if TYPE_CHECKING:
    from indico_assistant.plugin import AssistantPlugin


def create_nl2sql_pipeline(
    llm_service: LLMService,
    schema_file_path: str | None = None,
    db_session_factory: Callable[[], Any] | None = None,
    enable_cache: bool = True,
    cache_ttl_seconds: int = 600,
    cache_max_entries: int = 1000,
    max_rows: int = 1000,
    timeout_seconds: int = 30,
    max_correction_attempts: int = 3,
    allowed_tables: list[str] | None = None,
    embedding_service: EmbeddingService | None = None,
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
        db_session_factory: Factory for database sessions.
            If None, uses Indico's db.session.
        enable_cache: Whether to enable query caching (default: True).
        cache_ttl_seconds: Cache TTL in seconds (default: 600).
        cache_max_entries: Maximum cache entries (default: 1000).
        max_rows: Maximum rows to return (default: 1000).
        timeout_seconds: Query timeout (default: 30).
        max_correction_attempts: Max error corrections (default: 3).
        allowed_tables: Optional explicit table allowlist.
        embedding_service: Optional embedding service for vector search.

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
        cache=cache,
        max_rows=max_rows,
        timeout_seconds=timeout_seconds,
        max_correction_attempts=max_correction_attempts,
        allowed_tables=allowed_tables,
        embedding_service=embedding_service,
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
    - nl2sql_cache_ttl
    - nl2sql_allowed_tables

    Args:
        plugin: The AssistantPlugin instance.

    Returns:
        Configured NL2SQLPipeline instance.
    """
    from indico_assistant.services.llm import create_llm_service

    # Get LLM service from plugin
    llm_service = create_llm_service(plugin)

    # Read settings with defaults
    settings = plugin.settings
    timeout = settings.get("nl2sql_timeout", 30)
    max_rows = settings.get("nl2sql_max_rows", 1000)
    max_corrections = settings.get("nl2sql_max_corrections", 3)
    cache_ttl = settings.get("nl2sql_cache_ttl", 600)
    allowed_tables = settings.get("nl2sql_allowed_tables")

    embedding_service = create_embedding_service(plugin)

    return create_nl2sql_pipeline(
        llm_service=llm_service,
        enable_cache=cache_ttl > 0,
        cache_ttl_seconds=cache_ttl,
        max_rows=max_rows,
        timeout_seconds=timeout,
        max_correction_attempts=max_corrections,
        allowed_tables=allowed_tables,
        embedding_service=embedding_service,
    )
