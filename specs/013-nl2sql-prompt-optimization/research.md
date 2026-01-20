# Research: NL2SQL and Vector Search Prompt Optimization

**Feature**: 013-nl2sql-prompt-optimization  
**Date**: 2026-01-19  
**Status**: Complete

## Research Tasks

### R1: Current vs Reference Prompt Gap Analysis

**Question**: What are the specific differences between current prompts and the reference implementation?

**Findings**:

| Aspect | Current Implementation | Reference Implementation | Gap |
|--------|----------------------|-------------------------|-----|
| **Required Columns** | None specified | Always return event_id, event_title, event_start_dt, event_timezone | Missing standard output columns |
| **Date Formatting** | Raw timestamp output | `to_char(e.start_dt AT TIME ZONE e.timezone, 'Month DD YYYY, HH12:MI AM')` | No timezone-aware formatting |
| **Date Comparisons** | LLM may use hardcoded dates | "utilize PostgreSQL functionality to determine the current day" | May use stale dates |
| **Contributor Aggregation** | Basic JOINs | STRING_AGG with CONCAT for multi-field aggregation | Duplicate rows in output |
| **SQL Templates** | Generic rules only | Provides 3 complete SQL templates (events, attachments, vector search) | No examples for LLM to follow |
| **Foreign Key Hints** | JOIN hints table exists | Explicit text: "id in events.events is equivalent to event_id in events.persons" | Less explicit guidance |
| **Vector Search** | Separate RAGService | Part of generated SQL with `:query_vector` parameter | Architectural mismatch |
| **Vector Operator** | Uses `<=>` correctly in code | Explicit: "Do not use WHERE with similarity search... does NOT return a boolean" | Warning not in prompt |

**Decision**: Adopt reference patterns for all identified gaps. Create comprehensive prompt with templates.

---

### R2: pgvector Parameterized Query Best Practices

**Question**: How to safely substitute `:query_vector` placeholder in generated SQL?

**Findings**:

1. **SQLAlchemy text() with bindparams**:
   ```python
   from sqlalchemy import text, bindparam
   
   sql = text("""
       SELECT content_text, 1 - (embedding <=> :query_vector) as similarity
       FROM plugin_assistant.extracted_documents
       ORDER BY embedding <=> :query_vector
       LIMIT 10
   """)
   
   # Execute with vector as parameter
   result = session.execute(sql, {"query_vector": embedding_str})
   ```

2. **Vector Format**: PostgreSQL pgvector expects `'[0.1,0.2,0.3,...]'::vector` format
   - Can be passed as string and cast in SQL
   - Or use SQLAlchemy's custom type binding

3. **Detection Strategy**: Check if generated SQL contains `:query_vector` placeholder
   - If present: Generate embedding from user question, substitute before execution
   - If absent: Execute as normal

**Decision**: 
- Add `query_vector` parameter detection in `executor.py`
- Use `EmbeddingService.embed_text()` to generate query embedding
- Pass as string parameter with PostgreSQL vector cast

**Alternatives Considered**:
- Custom SQLAlchemy type for vectors → Rejected: Over-engineering for single use case
- Pre-process SQL to inject embedding → Rejected: SQL injection risk

---

### R3: Query Classification for Document vs Metadata

**Question**: How to reliably route document content queries to vector search SQL pattern?

**Findings**:

Current `classifier.py` intents:
- `event_query`, `registration_query`, `contribution_query`, `speaker_query`
- `session_query`, `attendee_query`, `schedule_query`, `attachment_query`
- `general_info`, `out_of_scope`

**Gap**: No `document_content_query` intent for vector search routing.

**Reference Keywords** (from `rag.py` DOCUMENT_KEYWORDS):
```python
DOCUMENT_KEYWORDS = {
    "presentation", "slide", "slides", "document", "paper", "pdf",
    "attachment", "file", "material", "says", "mentions", "according",
    "agenda", "schedule", "abstract", "summary", "content", "describe",
    "written", "stated", "talks about", "discusses", "explains"
}
```

**Distinction**:
- `attachment_query`: "What files are attached to event X?" → Metadata (filename, storage_id)
- `document_content_query`: "What does the presentation say about X?" → Vector search

**Decision**: 
- Add `document_content_query` intent to classifier
- Update classification hints to distinguish metadata vs content queries
- Generator selects SQL template based on intent

---

### R4: Guardrail Rationale Documentation

**Question**: Why are CTEs, subqueries, and window functions blocked?

**Findings**:

| Restriction | Rationale | Risk if Removed |
|-------------|-----------|-----------------|
| **CTEs (WITH)** | Can obscure malicious intent; adds prompt complexity | Moderate: Could hide subqueries; LLM may generate complex CTEs |
| **Subqueries** | Potential for exponential execution time; hard to validate | High: Unbounded nesting; resource exhaustion |
| **Window Functions** | Complex syntax; often misused by LLMs | Low: Primarily cosmetic concern |

**Constitution Check** (Principle IV - Graceful Degradation):
> "All external calls MUST have configurable timeouts"

Current executor already has 30s timeout, mitigating runaway query risk.

**Decision**: 
- Keep CTEs and subqueries blocked (per clarification Q2)
- Document rationale in prompt: "Use JOINs instead of subqueries for equivalent results"
- Provide explicit alternative patterns for common CTE use cases

---

### R5: Schema Context Enhancement Patterns

**Question**: What additional schema hints improve SQL generation quality?

**Findings from Reference Prompt**:

1. **Explicit Column Descriptions**:
   ```
   Pay attention to which column is in which table.
   Pay special attention to the Foreign Keys as they designate the relationships
   ```

2. **Recommended Columns for Context**:
   - Events: description, venue_name, room_name, address, type
   - Notes: html (contains meeting minutes)
   - Persons: first_name, last_name, affiliation, email
   - Contributions: title, description, duration

3. **Table Aliases** (already in `schema.py`):
   - `e` for events.events
   - `c` for events.contributions
   - `p` for events.persons
   - etc.

**Current `available_tables.yaml`**: Contains 1348 lines of schema definitions with types and descriptions.

**Decision**:
- Enhance `SchemaContext.get_schema_prompt()` to include "commonly useful columns" section
- Add explicit "for event queries, always include these columns" instruction
- Keep existing JOIN hints table structure

---

### R6: Embedding Service Integration

**Question**: How to expose embedding generation for query-time vector search?

**Current `EmbeddingService`**:
- `embed_text(text: str) -> list[float]` - Single text embedding
- `embed_batch(texts: list[str]) -> list[list[float]]` - Batch embedding
- Lazy model loading (doesn't load until first use)
- 384 dimensions (bge-small-en-v1.5)

**Integration Points**:
1. `ChatService._process_with_nl2sql()` - Currently calls RAGService separately
2. `QueryExecutor.execute()` - Needs to detect `:query_vector` and generate embedding

**Decision**:
- Create utility function `get_query_embedding(question: str) -> str` in executor or pipeline
- Returns PostgreSQL vector format string `'[0.1,0.2,...]'`
- Call when `:query_vector` detected in SQL

**Alternatives Considered**:
- Pass embedding through entire pipeline → Rejected: Unnecessary for non-vector queries
- Pre-compute in classifier → Rejected: Doesn't know if vector search will be used

## Summary of Decisions

| Area | Decision | Rationale |
|------|----------|-----------|
| Prompt Templates | Adopt reference SQL templates | Proven patterns, explicit guidance |
| Required Columns | Add event_id, title, start_dt, timezone | Actionable results |
| Date Formatting | Use to_char() with AT TIME ZONE | Human-readable, timezone-aware |
| Vector Search | Integrate into generated SQL | Unified architecture |
| Parameter Handling | SQLAlchemy text() with bindparams | Safe, standard approach |
| Classification | Add document_content_query intent | Route to vector SQL template |
| Guardrails | Keep CTEs/subqueries blocked | Security, per clarification |
| Schema Context | Add common columns section | Better LLM guidance |
