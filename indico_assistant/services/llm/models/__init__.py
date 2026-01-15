"""LLM response models package.

This package contains Pydantic models for LLM responses.
Note: LLMError is defined in errors.py and re-exported at the package level.
"""

from indico_assistant.services.llm.models.base import LLMResponse, HealthStatus
from indico_assistant.services.llm.models.classification import (
    Entity,
    TimeRange,
    QueryClassification,
)
from indico_assistant.services.llm.models.sql import (
    SQLGeneration,
    SQLCorrection,
)
from indico_assistant.services.llm.models.summary import ResponseSummary

__all__ = [
    # Base models
    "LLMResponse",
    "HealthStatus",
    # Classification models
    "Entity",
    "TimeRange",
    "QueryClassification",
    # SQL models
    "SQLGeneration",
    "SQLCorrection",
    # Summary models
    "ResponseSummary",
]
