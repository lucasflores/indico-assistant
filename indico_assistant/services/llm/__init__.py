"""LLM Service package for Indico Assistant.

This package provides an abstraction layer for LLM interactions using
the Instructor library with support for multiple providers.

Usage:
    >>> from indico_assistant.services.llm import LLMService, create_llm_service
    >>> from indico_assistant.services.llm import QueryClassification, SQLGeneration
    >>> 
    >>> llm = create_llm_service(plugin)
    >>> response = llm.generate("What events are today?", QueryClassification)
"""

from indico_assistant.services.llm.service import LLMService, create_llm_service
from indico_assistant.services.llm.factory import create_instructor_client
from indico_assistant.services.llm.errors import LLMError, ErrorType
from indico_assistant.services.llm.models import (
    LLMResponse,
    HealthStatus,
    Entity,
    TimeRange,
    QueryClassification,
    SQLGeneration,
    SQLCorrection,
    ResponseSummary,
)

__all__ = [
    # Service
    "LLMService",
    "create_llm_service",
    # Factory
    "create_instructor_client",
    # Errors
    "LLMError",
    "ErrorType",
    # Models
    "LLMResponse",
    "HealthStatus",
    "Entity",
    "TimeRange",
    "QueryClassification",
    "SQLGeneration",
    "SQLCorrection",
    "ResponseSummary",
]
