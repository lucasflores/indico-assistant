"""Indico Assistant services package.

This package contains service classes that encapsulate business logic
for the Indico Assistant plugin.

Services:
    - LLMService: Low-level LLM interaction service (from 002-llm-service-layer)
    - NL2SQLPipeline: Natural language to SQL translation pipeline (from 003-nl2sql-pipeline)
    - Observability: Langfuse tracing and metrics (from 005-langfuse-observability)
"""

from indico_assistant.services.llm import LLMService, create_llm_service
from indico_assistant.services.nl2sql import (
    NL2SQLPipeline,
    PipelineError,
    PipelineErrorType,
    PipelineResult,
    create_nl2sql_pipeline,
    create_nl2sql_pipeline_from_plugin,
)
from indico_assistant.services.observability import (
    get_langfuse_client,
    get_observability_logger,
)
from indico_assistant.services.observability.tracer import Tracer, create_tracer

__all__ = [
    # LLM Service (002)
    "LLMService",
    "create_llm_service",
    # NL2SQL Pipeline (003)
    "NL2SQLPipeline",
    "create_nl2sql_pipeline",
    "create_nl2sql_pipeline_from_plugin",
    "PipelineResult",
    "PipelineError",
    "PipelineErrorType",
    # Observability (005)
    "get_langfuse_client",
    "get_observability_logger",
    "Tracer",
    "create_tracer",
]
