# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
NL2SQL Pipeline Service Package.

This package provides natural language to SQL translation capabilities,
orchestrating question classification, SQL generation, validation,
execution, error correction, and result formatting.

Public API:
    - NL2SQLPipeline: Main orchestrator for NL→SQL→Results flow
    - create_nl2sql_pipeline: Factory function for pipeline creation
    - PipelineResult: Complete result from pipeline execution
    - PipelineError: Structured error information
    - PipelineErrorType: Error type enumeration
    - ValidationResult: SQL validation output
    - ExecutionResult: Query execution output
    - CachedResult: Cached query result wrapper

Components (for testing/extension):
    - QueryClassifier: Question classification component
    - SQLGenerator: SQL generation component
    - SQLValidator: SQL validation component
    - QueryExecutor: Query execution component
    - ErrorCorrector: Error correction component
    - ResultFormatter: Result formatting component
    - SchemaContext: Schema context provider
    - QueryCache: Query result cache
"""

from indico_assistant.services.nl2sql.models import (
    CachedResult,
    ExecutionResult,
    PipelineError,
    PipelineErrorType,
    PipelineResult,
    ValidationResult,
)

__all__ = [
    # Main pipeline
    "NL2SQLPipeline",
    "create_nl2sql_pipeline",
    # Result models
    "PipelineResult",
    "PipelineError",
    "PipelineErrorType",
    "ValidationResult",
    "ExecutionResult",
    "CachedResult",
    # Components (for testing/extension)
    "QueryClassifier",
    "SQLGenerator",
    "SQLValidator",
    "QueryExecutor",
    "ErrorCorrector",
    "ResultFormatter",
    "SchemaContext",
    "QueryCache",
    "create_nl2sql_pipeline_from_plugin",
]


# Lazy imports to avoid circular dependencies and speed up initial import
def __getattr__(name: str):
    """Lazy load components to avoid circular imports."""
    if name == "NL2SQLPipeline":
        from indico_assistant.services.nl2sql.pipeline import NL2SQLPipeline

        return NL2SQLPipeline
    elif name == "create_nl2sql_pipeline":
        from indico_assistant.services.nl2sql.factory import create_nl2sql_pipeline

        return create_nl2sql_pipeline
    elif name == "create_nl2sql_pipeline_from_plugin":
        from indico_assistant.services.nl2sql.factory import create_nl2sql_pipeline_from_plugin

        return create_nl2sql_pipeline_from_plugin
    elif name == "QueryClassifier":
        from indico_assistant.services.nl2sql.classifier import QueryClassifier

        return QueryClassifier
    elif name == "SQLGenerator":
        from indico_assistant.services.nl2sql.generator import SQLGenerator

        return SQLGenerator
    elif name == "SQLValidator":
        from indico_assistant.services.nl2sql.validator import SQLValidator

        return SQLValidator
    elif name == "QueryExecutor":
        from indico_assistant.services.nl2sql.executor import QueryExecutor

        return QueryExecutor
    elif name == "ErrorCorrector":
        from indico_assistant.services.nl2sql.corrector import ErrorCorrector

        return ErrorCorrector
    elif name == "ResultFormatter":
        from indico_assistant.services.nl2sql.formatter import ResultFormatter

        return ResultFormatter
    elif name == "SchemaContext":
        from indico_assistant.services.nl2sql.schema import SchemaContext

        return SchemaContext
    elif name == "QueryCache":
        from indico_assistant.services.nl2sql.cache import QueryCache

        return QueryCache
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
