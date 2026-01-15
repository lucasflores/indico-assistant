# Python API Contracts: LLM Service

**Feature**: 002-llm-service-layer  
**Date**: 2026-01-14

This document defines the Python API contracts for the LLM Service layer.
These are internal Python APIs, not REST endpoints.

---

## LLMService Class

### Constructor

```python
class LLMService:
    def __init__(self, plugin: "AssistantPlugin") -> None:
        """Initialize LLM service with plugin reference.
        
        Args:
            plugin: The AssistantPlugin instance for settings access.
        
        Note:
            The actual Instructor client is NOT created here.
            It is lazy-initialized on first generate() or health_check() call.
        """
```

### generate()

```python
from typing import TypeVar, Type

T = TypeVar("T", bound=BaseModel)

def generate(
    self,
    prompt: str,
    response_model: Type[T],
    *,
    system_prompt: str | None = None,
    max_retries: int | None = None,
    timeout: float | None = None,
) -> LLMResponse[T]:
    """Generate a structured LLM response.
    
    Args:
        prompt: The user prompt to send to the LLM.
        response_model: A Pydantic BaseModel class defining the expected response schema.
        system_prompt: Optional system prompt (defaults to plugin setting).
        max_retries: Override default max_retries from settings.
        timeout: Override default timeout from settings.
    
    Returns:
        LLMResponse[T] containing either:
        - success=True, result=T (validated response)
        - success=False, error=LLMError (structured error)
    
    Example:
        >>> response = llm_service.generate(
        ...     "What events are happening today?",
        ...     QueryClassification,
        ... )
        >>> if response.success:
        ...     print(response.result.intent)
        ... else:
        ...     print(f"Error: {response.error.message}")
    
    Notes:
        - Never raises exceptions to caller (all errors wrapped in LLMResponse)
        - Logs call metadata but NOT prompt/response content
        - Automatically retries on validation failures
    """
```

### health_check()

```python
def health_check(self) -> HealthStatus:
    """Test LLM provider connectivity.
    
    Returns:
        HealthStatus with:
        - status: "connected" | "unavailable" | "timeout" | "not_configured"
        - latency_ms: Response time in milliseconds (if connected)
        - provider: Configured provider name
        - model: Configured model name
        - error: Error message (if not connected)
    
    Example:
        >>> status = llm_service.health_check()
        >>> print(f"LLM status: {status.status}, latency: {status.latency_ms}ms")
    
    Notes:
        - Uses a minimal test prompt to verify full connectivity
        - Respects configured timeout
        - Does not count against rate limits on most providers
    """
```

---

## Factory Function

```python
def create_llm_service(plugin: "AssistantPlugin") -> LLMService:
    """Create an LLM service instance for the plugin.
    
    This is the primary way to obtain an LLMService instance.
    The service maintains a reference to the plugin for settings access.
    
    Args:
        plugin: The AssistantPlugin instance.
    
    Returns:
        Configured LLMService instance.
    
    Example:
        >>> from indico_assistant.services.llm import create_llm_service
        >>> llm = create_llm_service(plugin)
    """
```

---

## Response Models

### LLMResponse[T]

```python
from typing import Generic, TypeVar
from pydantic import BaseModel, model_validator

T = TypeVar("T", bound=BaseModel)

class LLMResponse(BaseModel, Generic[T]):
    """Generic response wrapper for LLM calls.
    
    Attributes:
        success: Whether the LLM call succeeded.
        result: The validated response model (if success=True).
        error: The structured error (if success=False).
        latency_ms: Call duration in milliseconds.
        retries: Number of retry attempts made.
    
    Invariants:
        - If success=True: result is not None, error is None
        - If success=False: result is None, error is not None
    """
    success: bool
    result: T | None = None
    error: "LLMError | None" = None
    latency_ms: int
    retries: int = 0
    
    @model_validator(mode="after")
    def check_consistency(self) -> "LLMResponse[T]":
        if self.success and self.result is None:
            raise ValueError("success=True requires result")
        if not self.success and self.error is None:
            raise ValueError("success=False requires error")
        return self
```

### LLMError

```python
from enum import Enum

class ErrorType(str, Enum):
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION_ERROR = "authentication_error"
    VALIDATION_ERROR = "validation_error"
    MODEL_NOT_FOUND = "model_not_found"
    NOT_CONFIGURED = "not_configured"
    UNKNOWN_ERROR = "unknown_error"

class LLMError(BaseModel):
    """Structured error for LLM failures.
    
    Attributes:
        error_type: Categorized error type for programmatic handling.
        message: Human-readable error description.
        details: Additional error context (optional).
        retry_after: Seconds to wait before retry (for rate_limit).
    """
    error_type: ErrorType
    message: str
    details: dict | None = None
    retry_after: int | None = None
```

### HealthStatus

```python
class HealthStatus(BaseModel):
    """Health check result for LLM provider.
    
    Attributes:
        status: Provider status.
        latency_ms: Response time in milliseconds (if connected).
        provider: Configured provider name.
        model: Configured model name.
        error: Error message (if not connected).
    """
    status: Literal["connected", "unavailable", "timeout", "not_configured"]
    latency_ms: int | None = None
    provider: str
    model: str
    error: str | None = None
```

---

## Pre-defined Response Models

### QueryClassification

```python
class Entity(BaseModel):
    """Extracted entity from user query."""
    type: str  # person, event, room, date, etc.
    value: str
    confidence: float = Field(ge=0.0, le=1.0)

class TimeRange(BaseModel):
    """Temporal constraint from user query."""
    start: str | None = None  # ISO date or relative
    end: str | None = None

class QueryClassification(BaseModel):
    """Classification of user natural language query.
    
    Example output:
        {
            "intent": "search_events",
            "entities": [
                {"type": "person", "value": "John Smith", "confidence": 0.95}
            ],
            "time_range": {"start": "2026-01-14", "end": "2026-01-21"},
            "filters": {"category": "workshop"}
        }
    """
    intent: str
    entities: list[Entity] = Field(default_factory=list)
    time_range: TimeRange | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
```

### SQLGeneration

```python
class SQLGeneration(BaseModel):
    """LLM-generated SQL query with explanation.
    
    Example output:
        {
            "query": "SELECT e.title, e.start_dt FROM events.events e WHERE ...",
            "explanation": "This query retrieves event titles and start dates...",
            "tables_used": ["events.events", "events.contributions"]
        }
    """
    query: str = Field(description="Generated SQL SELECT statement")
    explanation: str = Field(description="Natural language explanation")
    tables_used: list[str] = Field(min_length=1)
    
    @field_validator("query")
    @classmethod
    def validate_sql_safety(cls, v: str) -> str:
        upper = v.upper().strip()
        if not upper.startswith("SELECT"):
            raise ValueError("Query must be a SELECT statement")
        forbidden = ["DROP", "DELETE", "INSERT", "UPDATE", "CREATE", "ALTER", "TRUNCATE"]
        for keyword in forbidden:
            if keyword in upper:
                raise ValueError(f"Query cannot contain {keyword}")
        return v
```

### SQLCorrection

```python
class SQLCorrection(BaseModel):
    """Corrected SQL query after error feedback.
    
    Example output:
        {
            "corrected_query": "SELECT e.title FROM events.events e WHERE ...",
            "error_analysis": "The original query referenced a non-existent column 'name'...",
            "changes_made": ["Changed 'name' to 'title'", "Added proper table alias"]
        }
    """
    corrected_query: str
    error_analysis: str
    changes_made: list[str] = Field(min_length=1)
    
    @field_validator("corrected_query")
    @classmethod
    def validate_sql_safety(cls, v: str) -> str:
        # Same validation as SQLGeneration
        ...
```

### ResponseSummary

```python
class ResponseSummary(BaseModel):
    """Natural language response with confidence scoring.
    
    Example output:
        {
            "answer": "There are 5 workshops scheduled for next week...",
            "confidence": 0.92,
            "sources": ["events.events", "events.contributions"]
        }
    """
    answer: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)
```

---

## Usage Examples

### Basic Generate Call

```python
from indico_assistant.services.llm import LLMService, QueryClassification

# Assuming llm_service is available via plugin
response = llm_service.generate(
    prompt="Show me all workshops next week",
    response_model=QueryClassification,
)

if response.success:
    classification = response.result
    print(f"Intent: {classification.intent}")
    print(f"Entities: {classification.entities}")
else:
    print(f"Error ({response.error.error_type}): {response.error.message}")
```

### Custom Response Model

```python
from pydantic import BaseModel

class EventSummary(BaseModel):
    title: str
    description: str
    key_topics: list[str]

response = llm_service.generate(
    prompt=f"Summarize this event: {event_data}",
    response_model=EventSummary,
    timeout=60.0,  # Longer timeout for complex task
)
```

### Health Check in Controller

```python
def get_health_status():
    llm_status = llm_service.health_check()
    return {
        "llm": {
            "status": llm_status.status,
            "latency_ms": llm_status.latency_ms,
            "provider": llm_status.provider,
            "model": llm_status.model,
        }
    }
```
