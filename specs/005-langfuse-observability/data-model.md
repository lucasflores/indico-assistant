# Data Model: Langfuse Observability

**Feature**: 005-langfuse-observability  
**Date**: 2026-01-15

## Overview

This feature introduces three new PostgreSQL tables in the `plugin_assistant` schema to store locally cached observability metrics synced from Langfuse. These tables support the admin dashboard API and ensure metrics availability when Langfuse is unreachable.

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Langfuse Cloud                                │
│  ┌─────────┐    ┌─────────┐    ┌──────────────┐                │
│  │ Traces  │───>│  Spans  │───>│ Generations  │                │
│  └─────────┘    └─────────┘    └──────────────┘                │
└─────────────────────────────────────────────────────────────────┘
        │                                                          
        │ Hourly Sync (Celery)                                    
        ▼                                                          
┌─────────────────────────────────────────────────────────────────┐
│                plugin_assistant schema                           │
│                                                                  │
│  ┌──────────────────┐     ┌──────────────────┐                 │
│  │ UsageStats       │     │ ErrorRecord      │                 │
│  ├──────────────────┤     ├──────────────────┤                 │
│  │ id (PK, UUID)    │     │ id (PK, UUID)    │                 │
│  │ period_type      │     │ correlation_id   │                 │
│  │ period_start     │     │ timestamp        │                 │
│  │ total_queries    │     │ error_type       │                 │
│  │ avg_latency_ms   │     │ error_message    │                 │
│  │ error_count      │     │ stack_trace      │                 │
│  │ queries_by_intent│     │ user_id_hash     │                 │
│  │ last_synced_at   │     │ session_id       │                 │
│  └──────────────────┘     │ created_at       │                 │
│                           └──────────────────┘                 │
│  ┌──────────────────┐                                          │
│  │ MetricsSyncLog   │                                          │
│  ├──────────────────┤                                          │
│  │ id (PK, UUID)    │                                          │
│  │ started_at       │                                          │
│  │ completed_at     │                                          │
│  │ records_synced   │                                          │
│  │ status           │                                          │
│  │ error_message    │                                          │
│  └──────────────────┘                                          │
└─────────────────────────────────────────────────────────────────┘
```

## Entities

### UsageStats

Stores aggregated usage statistics for configurable time periods.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Unique identifier |
| period_type | String(20) | NOT NULL, CHECK(day/week/month) | Aggregation period type |
| period_start | DateTime | NOT NULL | Start of the period (UTC) |
| total_queries | Integer | NOT NULL, DEFAULT 0 | Total queries in period |
| successful_queries | Integer | NOT NULL, DEFAULT 0 | Queries that completed without error |
| avg_latency_ms | Float | NULLABLE | Average response latency |
| p95_latency_ms | Float | NULLABLE | 95th percentile latency |
| error_count | Integer | NOT NULL, DEFAULT 0 | Total errors in period |
| error_rate | Float | COMPUTED | error_count / total_queries |
| queries_by_intent | JSON | NULLABLE | {"count_query": 50, "search": 30, ...} |
| total_input_tokens | Integer | NOT NULL, DEFAULT 0 | Sum of input tokens |
| total_output_tokens | Integer | NOT NULL, DEFAULT 0 | Sum of output tokens |
| last_synced_at | DateTime | NOT NULL | When this record was last updated |
| created_at | DateTime | NOT NULL, DEFAULT now() | Record creation timestamp |

**Indexes**:
- `ix_usage_stats_period` on (period_type, period_start)
- `ix_usage_stats_sync` on (last_synced_at)

**Unique Constraint**: (period_type, period_start)

### ErrorRecord

Stores recent errors for debugging (rolling 7-day window).

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Unique identifier |
| correlation_id | String(64) | NOT NULL, INDEX | Request correlation ID for tracing |
| timestamp | DateTime | NOT NULL, INDEX | When error occurred (UTC) |
| error_type | String(100) | NOT NULL, INDEX | Error classification (LLM_TIMEOUT, SQL_ERROR, etc.) |
| error_message | Text | NOT NULL | Human-readable error description |
| stack_trace | Text | NULLABLE | Full stack trace (only at "full" privacy level) |
| user_id_hash | String(64) | NULLABLE | SHA-256 hash of user ID (for correlation, not PII) |
| session_id | UUID | NULLABLE, FK→ChatSession | Associated chat session if available |
| langfuse_trace_id | String(64) | NULLABLE | Link to Langfuse trace for detailed view |
| created_at | DateTime | NOT NULL, DEFAULT now() | Record creation timestamp |

**Indexes**:
- `ix_error_record_timestamp` on (timestamp DESC)
- `ix_error_record_type` on (error_type)
- `ix_error_record_correlation` on (correlation_id)

### MetricsSyncLog

Tracks synchronization jobs from Langfuse to local storage.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Unique identifier |
| started_at | DateTime | NOT NULL | When sync job started |
| completed_at | DateTime | NULLABLE | When sync job completed (NULL if running/failed) |
| period_start | DateTime | NOT NULL | Start of period being synced |
| period_end | DateTime | NOT NULL | End of period being synced |
| traces_processed | Integer | NOT NULL, DEFAULT 0 | Number of Langfuse traces processed |
| stats_updated | Integer | NOT NULL, DEFAULT 0 | Number of UsageStats records updated |
| errors_recorded | Integer | NOT NULL, DEFAULT 0 | Number of ErrorRecord records created |
| status | String(20) | NOT NULL, CHECK(running/completed/failed) | Sync job status |
| error_message | Text | NULLABLE | Error message if status=failed |

**Indexes**:
- `ix_sync_log_started` on (started_at DESC)
- `ix_sync_log_status` on (status)

## State Transitions

### MetricsSyncLog Status

```
running ─────> completed
   │
   └─────────> failed
```

### ErrorRecord Lifecycle

- Created when error occurs during traced operation
- Automatically deleted after 7 days via cleanup task
- No state transitions (immutable after creation)

## Validation Rules

### UsageStats
- period_type must be one of: 'day', 'week', 'month'
- period_start must be start of day/week/month boundary
- total_queries >= successful_queries >= 0
- error_count >= 0
- avg_latency_ms >= 0 if not null
- error_rate computed as error_count / total_queries (or 0 if total_queries = 0)

### ErrorRecord
- correlation_id must be valid hex string (32-64 chars)
- error_type must be from allowed enum (defined in code)
- timestamp must not be in future
- stack_trace only populated when privacy_level = "full"

### MetricsSyncLog
- completed_at must be >= started_at if not null
- period_end must be > period_start
- traces_processed, stats_updated, errors_recorded >= 0

## Error Types Enum

```python
class ObservabilityErrorType(str, Enum):
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    LLM_VALIDATION = "LLM_VALIDATION"
    LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
    SQL_SYNTAX_ERROR = "SQL_SYNTAX_ERROR"
    SQL_EXECUTION_ERROR = "SQL_EXECUTION_ERROR"
    SQL_TIMEOUT = "SQL_TIMEOUT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
```

## Migration Notes

- Migration: `003_create_observability_tables.py`
- All tables in `plugin_assistant` schema
- Uses UUID primary keys (consistent with Feature 004)
- JSON column for queries_by_intent requires PostgreSQL 9.4+
- No foreign keys to Langfuse (external system)
- session_id FK to ChatSession is optional (SET NULL on delete)
