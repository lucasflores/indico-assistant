# Data Model: LLM Service Abstraction Layer

**Feature**: 002-llm-service-layer  
**Date**: 2026-01-14

## Entity Relationship Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         LLMService                               │
│  ┌───────────────┐   ┌─────────────────┐   ┌────────────────┐  │
│  │ Instructor    │   │ PluginSettings  │   │ Logger         │  │
│  │ Client        │◄──│ (from plugin)   │   │                │  │
│  └───────────────┘   └─────────────────┘   └────────────────┘  │
│         │                                                        │
│         │ generate(prompt, ResponseModel)                        │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              LLMResponse[T]                                  ││
│  │  ┌─────────────────┐     ┌─────────────────────────────┐   ││
│  │  │ Success         │ OR  │ Error                       │   ││
│  │  │ result: T       │     │ error: LLMError             │   ││
│  │  └─────────────────┘     └─────────────────────────────┘   ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘

Response Models (Pydantic BaseModel subclasses):
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│QueryClassification│ │SQLGeneration     │ │ResponseSummary   │
├──────────────────┤ ├──────────────────┤ ├──────────────────┤
│intent: str       │ │query: str        │ │answer: str       │
│entities: list    │ │explanation: str  │ │confidence: float │
│time_range: opt   │ │tables_used: list │ │sources: list     │
│filters: dict     │ └──────────────────┘ └──────────────────┘
└──────────────────┘
                     ┌──────────────────┐
                     │SQLCorrection     │
                     ├──────────────────┤
                     │corrected_query   │
                     │error_analysis    │
                     │changes_made: list│
                     └──────────────────┘
```

---

## Core Entities

### 1. LLMService

**Purpose**: Main service class providing LLM interaction capabilities.

| Attribute | Type | Description |
|-----------|------|-------------|
| _client | Instructor \| None | Lazy-initialized Instructor client |
| _plugin | AssistantPlugin | Reference to plugin for settings access |
| _logger | Logger | Structured logger for observability |

| Method | Signature | Description |
|--------|-----------|-------------|
| generate | `generate[T](prompt: str, response_model: Type[T], **kwargs) -> LLMResponse[T]` | Make structured LLM call |
| health_check | `health_check() -> HealthStatus` | Test provider connectivity |
| _create_client | `_create_client() -> Instructor` | Factory for Instructor client |
| _get_settings | `_get_settings() -> LLMSettings` | Extract current settings from plugin |

**Lifecycle**: Singleton per plugin, lazy-initialized on first `generate()` or `health_check()` call.

---

### 2. LLMError

**Purpose**: Structured error response for all LLM failures.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| error_type | ErrorType | Yes | Enum: timeout, connection_error, rate_limit, authentication_error, validation_error, model_not_found, not_configured, unknown_error |
| message | str | Yes | Human-readable error description |
| details | dict \| None | No | Additional error context (provider response, etc.) |
| retry_after | int \| None | No | Seconds to wait before retry (for rate_limit) |

**Validation Rules**:
- `error_type` must be valid enum value
- `message` cannot be empty
- `retry_after` must be positive if present

---

### 3. LLMResponse[T]

**Purpose**: Generic wrapper for LLM call results (success or error).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| success | bool | Yes | Whether the call succeeded |
| result | T \| None | Conditional | The validated response (if success=True) |
| error | LLMError \| None | Conditional | The error details (if success=False) |
| latency_ms | int | Yes | Call duration in milliseconds |
| retries | int | Yes | Number of retry attempts made |

**Validation Rules**:
- If `success=True`, `result` must be present and `error` must be None
- If `success=False`, `error` must be present and `result` must be None
- `latency_ms` must be non-negative
- `retries` must be non-negative

---

### 4. HealthStatus

**Purpose**: Health check result for LLM provider.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| status | str | Yes | One of: "connected", "unavailable", "timeout", "not_configured" |
| latency_ms | int \| None | No | Response time (only if connected) |
| provider | str | Yes | Configured provider name |
| model | str | Yes | Configured model name |
| error | str \| None | No | Error message (if not connected) |

---

## Pre-defined Response Models

### 5. QueryClassification

**Purpose**: Classify user natural language query intent.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| intent | str | Yes | - | Primary intent (e.g., "search_events", "get_statistics", "list_speakers") |
| entities | list[Entity] | Yes | [] | Extracted named entities |
| time_range | TimeRange \| None | No | None | Temporal constraints if present |
| filters | dict[str, Any] | Yes | {} | Additional filter criteria |

**Nested: Entity**

| Field | Type | Description |
|-------|------|-------------|
| type | str | Entity type (person, event, room, date, etc.) |
| value | str | Extracted value |
| confidence | float | Extraction confidence (0.0-1.0) |

**Nested: TimeRange**

| Field | Type | Description |
|-------|------|-------------|
| start | str \| None | ISO date string or relative ("today", "this week") |
| end | str \| None | ISO date string or relative |

---

### 6. SQLGeneration

**Purpose**: LLM-generated SQL query with explanation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| query | str | Yes | Generated SQL SELECT statement |
| explanation | str | Yes | Natural language explanation of what the query does |
| tables_used | list[str] | Yes | List of table names referenced |

**Validation Rules**:
- `query` must start with SELECT (case-insensitive)
- `query` must not contain DDL keywords (DROP, CREATE, ALTER, TRUNCATE)
- `tables_used` must not be empty

---

### 7. SQLCorrection

**Purpose**: Corrected SQL query after error feedback.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| corrected_query | str | Yes | Fixed SQL query |
| error_analysis | str | Yes | Analysis of what was wrong |
| changes_made | list[str] | Yes | List of corrections applied |

**Validation Rules**:
- Same SQL safety rules as SQLGeneration
- `changes_made` should not be empty

---

### 8. ResponseSummary

**Purpose**: Natural language response with confidence scoring.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| answer | str | Yes | Natural language response to user |
| confidence | float | Yes | Confidence score (0.0-1.0) |
| sources | list[str] | Yes | Data sources used (table names, etc.) |

**Validation Rules**:
- `confidence` must be between 0.0 and 1.0
- `answer` cannot be empty

---

## Enums

### ErrorType

```python
class ErrorType(str, Enum):
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION_ERROR = "authentication_error"
    VALIDATION_ERROR = "validation_error"
    MODEL_NOT_FOUND = "model_not_found"
    NOT_CONFIGURED = "not_configured"
    UNKNOWN_ERROR = "unknown_error"
```

### ProviderType

```python
class ProviderType(str, Enum):
    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"
    OPENAI = "openai"
```

---

## State Transitions

### LLMService Lifecycle

```
                    ┌─────────────┐
                    │ UNINITIALIZED│
                    └──────┬──────┘
                           │ first generate() or health_check()
                           ▼
             ┌─────────────────────────┐
             │ INITIALIZING            │
             │ (creating client)       │
             └────────────┬────────────┘
                          │
            ┌─────────────┼─────────────┐
            │ success     │             │ failure
            ▼             │             ▼
    ┌───────────────┐     │     ┌───────────────┐
    │ READY         │     │     │ DEGRADED      │
    │ (client ready)│     │     │ (no client)   │
    └───────────────┘     │     └───────────────┘
            │             │             │
            │ settings    │             │ retry on
            │ change      │             │ next call
            └─────────────┴─────────────┘
```

**Note**: State is implicit (based on `_client` being None or not). No explicit state machine needed.

---

## Data Flow

### Generate Call Flow

```
1. Caller → LLMService.generate(prompt, ResponseModel)
2. LLMService → Check/Initialize client
3. LLMService → Start timer
4. LLMService → client.create(messages, response_model, max_retries)
5. Instructor → Provider API call
6. Provider → Response (or error)
7. Instructor → Validate against ResponseModel
8. If validation fails and retries remaining:
   8a. Instructor → Send validation error to LLM
   8b. Go to step 5
9. LLMService → Stop timer, calculate latency
10. LLMService → Log metadata (no content)
11. LLMService → Return LLMResponse[T]
```

---

## Index & Query Patterns

N/A - This feature is stateless. No database storage.

---

## Migration Notes

N/A - No database schema changes required.
