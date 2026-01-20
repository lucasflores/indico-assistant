# Contract: Features Section

## Section Requirements

**Location**: After Table of Contents, before Requirements  
**Purpose**: Provide comprehensive overview of all implemented capabilities  
**Format**: Bullet list with grouped features

## Content Structure

### Header
```markdown
## Features
```

### Feature Groups

#### Group 1: Core Capabilities
- **Natural Language Queries**: Ask questions about event data using natural language
- **Conversation History**: Multi-turn conversations with context awareness - ask follow-up questions using pronouns ("the first one", "that meeting") and contextual references
- **NL2SQL Pipeline**: Translates natural language to SQL with validation, permission filtering, and security constraints

#### Group 2: LLM Integration
- **Multiple LLM Providers**: Support for Ollama (local), HuggingFace Router, and OpenAI-compatible APIs
- **Structured Outputs**: All LLM responses validated via Pydantic models with automatic retry logic
- **Provider Abstraction**: Swap LLM providers via configuration without code changes

#### Group 3: Document Intelligence
- **Vector Search RAG**: Semantic search across documents using pgvector and sentence-transformers embeddings
- **Real-time Document Indexing**: Automatically indexes PDF, DOCX, DOC, TXT, and Markdown files when uploaded as attachments, making them immediately searchable
  - Immediate Search: Documents become searchable within seconds of upload
  - Duplicate Detection: Skips re-indexing identical documents based on content hash
  - Graceful Degradation: Continues working even when vector search is unavailable
  - File Size Tiers: Fast indexing (<10MB), best-effort (10-50MB), automatic rejection (>50MB)
  - Supported Formats: PDF, DOCX, DOC, TXT, MD (silently ignores images, videos, archives)

#### Group 4: User Interface
- **Embedded Chat Widget**: Chainlit Copilot widget injected on every page with JWT auth, theme sync, persistence, and feedback
  - JWT Authentication: Secure token-based auth per user
  - Theme Synchronization: Auto-detects Indico theme and applies matching styles
  - Session Persistence: Conversations persist across page reloads
  - Feedback Mechanism: Thumbs up/down with optional comments
  - Graceful Degradation: Loading/error states, hidden when not ready

#### Group 5: Configuration & Management
- **Per-Event Configuration**: Customize assistant behavior for specific events
- **Health Monitoring**: Built-in health check endpoint for monitoring
- **CLI Tools**: Command-line interface for administration and diagnostics

#### Group 6: Observability & Quality
- **Langfuse Observability**: Integrated tracing and monitoring for all LLM interactions with privacy filters
- **Test Coverage**: Comprehensive unit, integration, and contract tests (80%+ coverage on services)

## Content Requirements

1. **Each feature MUST have**:
   - Clear name in bold
   - 1-3 sentence description
   - Key value proposition

2. **Sub-features (where applicable) MUST include**:
   - Indented bullet points
   - Specific capabilities or behaviors
   - Technical constraints (file sizes, formats, etc.)

3. **Links to detailed docs**:
   - Vector search → "See [Vector Search Setup](docs/VECTOR_SEARCH_SETUP.md)"
   - Chat widget → "See [Deployment Guide](docs/DEPLOYMENT.md)"
   - Observability → "See [Langfuse Setup](docs/LANGFUSE_SETUP.md)"

## Verification Checklist

- [ ] All 13 features represented (may be grouped logically)
- [ ] Each feature has 1-3 sentence description
- [ ] Technical details match implementation (file formats, size limits, etc.)
- [ ] Links to external docs are included where relevant
- [ ] Grouped logically for readability (not spec number order)
- [ ] No implementation details (languages, specific libraries)
- [ ] Focus on user value and capabilities

## Examples

**Good**:
```markdown
- **Real-time Document Indexing**: Automatically indexes PDF, DOCX, DOC, TXT, and Markdown files when uploaded as attachments, making them immediately searchable
```

**Bad** (too technical):
```markdown
- **Real-time Document Indexing**: Uses PyPDF2 and python-docx extractors with sentence-transformers embeddings stored in pgvector via attachment_created signal handler
```

## Success Criteria

- Feature list comprehensible to non-technical event managers
- Developers can identify all major capabilities at a glance
- Links provide path to detailed technical information
- Reading time: 2-3 minutes for entire Features section
