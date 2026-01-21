# Quickstart: Chat Source Citations

**Feature**: 015-chat-source-citations  
**Date**: 2026-01-20  
**For**: Developers implementing citation support

## Overview

This feature adds automatic source citations to chat responses. Citations appear as inline markdown links that users can click to view the original source (event page or document attachment).

**Key Points**:
- Citations embedded as `[source](url)` markdown links in response text
- Event-sourced info links to event pages: `http://base/event/7/`
- Document-sourced info links to attachments: `http://base/event/7/contributions/3/attachments/4/6/file.pdf`
- Citations added incrementally during streaming responses
- Graceful degradation: missing metadata doesn't break responses

---

## Quick Start

### 1. Install/Setup

No new dependencies required. Uses existing Python stdlib (`urllib.parse` for URL encoding).

```bash
# No pip install needed
# Feature uses existing project dependencies
```

### 2. Basic Usage

```python
from indico_assistant.services.chat.citations import CitationBuilder, SourceCitation

# Initialize builder with base URL from plugin settings
builder = CitationBuilder(base_url="http://localhost:8000")

# Build event citation
event_cite = builder.build_event_citation(event_id=7)
print(event_cite)
# Output: "[source](http://localhost:8000/event/7/)"

# Build document citation
doc_cite = builder.build_document_citation(
    event_id=7,
    contribution_id=3,
    attachment_id=4,
    file_id=6,
    filename="paper.pdf"
)
print(doc_cite)
# Output: "[source](http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf)"
```

### 3. Integration with Chat Service

```python
from indico_assistant.services.chat import ChatService
from indico_assistant.services.chat.citations import CitationBuilder

# In ChatService.send_message()
builder = CitationBuilder(base_url=self._get_base_url())

# After NL2SQL execution
if nl2sql_response.source_event_ids:
    event_citations = [
        builder.build_event_citation(event_id)
        for event_id in nl2sql_response.source_event_ids
    ]
    # Include in LLM prompt

# After RAG context retrieval
if rag_results:
    doc_citations = []
    for result in rag_results:
        if result.metadata.get('contribution_id') and result.metadata.get('file_id'):
            cite = builder.build_document_citation(
                event_id=result.event_id,
                contribution_id=result.metadata['contribution_id'],
                attachment_id=result.attachment_id,
                file_id=result.metadata['file_id'],
                filename=result.metadata.get('filename', 'document')
            )
            doc_citations.append(cite)
    # Include in LLM prompt
```

### 4. LLM Prompt Template

```python
system_prompt = """
You are a helpful assistant for event management.

When providing information, cite your sources using this format:
- For event information: The workshop is on January 25th [source](url)
- For document information: According to the paper [source](url), ...

Available citations for this response:
{citations}

Always include citations when using the provided information.
"""

# Format available citations
available_citations = "\n".join([
    f"- Event {event_id}: {builder.build_event_citation(event_id)}"
    for event_id in source_event_ids
] + [
    f"- Document {filename}: {doc_citation}"
    for filename, doc_citation in doc_citations_map.items()
])

formatted_prompt = system_prompt.format(citations=available_citations)
```

---

## Common Patterns

### Pattern 1: Event Citation from NL2SQL

```python
# In NL2SQL pipeline response handler
def add_event_citations(self, event_ids: list[int]) -> list[str]:
    """Generate citations for events in query results."""
    builder = CitationBuilder(base_url=self._get_base_url())
    return [builder.build_event_citation(eid) for eid in event_ids]

# Usage
if nl2sql_response.success and nl2sql_response.source_event_ids:
    citations = self.add_event_citations(nl2sql_response.source_event_ids)
    # Add to metadata.data_sources
```

### Pattern 2: Document Citation from Vector Search

```python
# In RAG service after search
def extract_document_citations(
    self, 
    search_results: list[SearchResult]
) -> list[SourceCitation]:
    """Extract unique document citations from search results."""
    builder = CitationBuilder(base_url=self._get_base_url())
    seen = set()
    citations = []
    
    for result in search_results:
        meta = result.metadata
        # Create unique key
        key = (result.event_id, meta.get('attachment_id'), meta.get('file_id'))
        
        if key in seen or not all(key):
            continue
        seen.add(key)
        
        # Build citation
        cite = SourceCitation(
            type="document",
            event_id=result.event_id,
            contribution_id=meta['contribution_id'],
            attachment_id=meta['attachment_id'],
            file_id=meta['file_id'],
            filename=meta.get('filename', 'document'),
            url=builder.build_document_url(
                result.event_id,
                meta['contribution_id'],
                result.attachment_id,
                meta['file_id'],
                meta.get('filename', 'document')
            ),
            description=f"Document: {meta.get('filename', 'document')}"
        )
        citations.append(cite)
    
    return citations
```

### Pattern 3: Response with Multiple Source Types

```python
# Combining event and document citations
def build_response_with_citations(
    self,
    nl2sql_response,
    rag_results
) -> ResponseWithCitations:
    """Build LLM response model with mixed citations."""
    
    all_citations = []
    
    # Add event citations
    if nl2sql_response and nl2sql_response.source_event_ids:
        event_cites = self.extract_event_citations(nl2sql_response.source_event_ids)
        all_citations.extend(event_cites)
    
    # Add document citations
    if rag_results:
        doc_cites = self.extract_document_citations(rag_results)
        all_citations.extend(doc_cites)
    
    # Generate LLM response with citations
    llm_response = self._llm_service.generate(
        prompt=self._build_prompt_with_citations(all_citations),
        response_model=ResponseWithCitations
    )
    
    return llm_response.result
```

---

## Configuration

### Plugin Settings

Add base URL configuration to plugin settings:

```python
# In indico_assistant/default_settings.py
default_settings = {
    # ... existing settings ...
    
    'base_url': {
        'type': 'str',
        'default': 'http://localhost:8000',
        'description': 'Base URL for Indico instance (used in citation links)'
    }
}
```

### Per-Event Override

```python
# Event managers can override base URL
def _get_base_url(self, event_id: int | None = None) -> str:
    """Get base URL with event override support."""
    if event_id:
        # Check for event-specific override
        event_settings = self._plugin.event_settings.get(event_id, 'base_url')
        if event_settings:
            return event_settings
    
    # Fall back to global setting
    return self._plugin.settings.get('base_url') or 'http://localhost:8000'
```

---

## Testing Examples

### Unit Test: Citation Builder

```python
def test_citation_builder_event(self):
    """Test event citation construction."""
    builder = CitationBuilder("http://localhost:8000")
    
    # Test URL construction
    url = builder.build_event_url(7)
    assert url == "http://localhost:8000/event/7/"
    
    # Test markdown citation
    cite = builder.build_event_citation(7)
    assert cite == "[source](http://localhost:8000/event/7/)"

def test_citation_builder_document_encoding(self):
    """Test filename URL encoding."""
    builder = CitationBuilder("http://localhost:8000")
    
    # Test with space in filename
    url = builder.build_document_url(7, 3, 4, 6, "my paper.pdf")
    assert "my%20paper.pdf" in url
    
    # Test special characters
    url = builder.build_document_url(7, 3, 4, 6, "résumé.pdf")
    assert "r%C3%A9sum%C3%A9.pdf" in url
```

### Integration Test: End-to-End Citations

```python
def test_chat_with_citations(test_client, plugin):
    """Test chat response includes citations."""
    response = test_client.post('/api/assistant/chat', json={
        'message': 'When is the workshop?',
        'event_id': 7
    })
    
    assert response.status_code == 200
    data = response.json()
    
    # Check response includes citation
    assert '[source]' in data['response']
    assert 'http://localhost:8000/event/7/' in data['response']
    
    # Check metadata includes structured citations
    assert 'data_sources' in data['metadata']
    sources = data['metadata']['data_sources']
    assert len(sources) > 0
    assert sources[0]['type'] == 'event'
    assert sources[0]['event_id'] == 7
```

---

## Troubleshooting

### Citations Not Appearing

**Problem**: Response generated but no `[source](url)` links present.

**Checks**:
1. Verify `base_url` configured in plugin settings
2. Check LLM prompt includes citation instructions
3. Verify source metadata available (event_ids or document metadata)
4. Check logs for citation generation warnings

```python
# Add debug logging
logger.debug(f"Available event citations: {event_citations}")
logger.debug(f"Available doc citations: {doc_citations}")
logger.debug(f"LLM response: {llm_response.answer[:100]}")
```

### Broken Citation Links

**Problem**: Citations present but links return 404.

**Checks**:
1. Verify URL structure matches Indico's actual routes
2. Check `contribution_id` and `file_id` in document metadata
3. Verify event/attachment still exists (not deleted)
4. Check user permissions for cited resources

```python
# Test citation URL
import requests
response = requests.head(citation_url)
if response.status_code != 200:
    logger.warning(f"Citation URL invalid: {citation_url} -> {response.status_code}")
```

### Missing Document Metadata

**Problem**: Vector search results lack `contribution_id` or `file_id`.

**Solution**: Update document indexing to capture full metadata:

```python
# In indico_assistant/tasks/indexing.py
def extract_attachment_metadata(attachment) -> dict:
    """Extract full metadata from Indico attachment."""
    return {
        'filename': attachment.file.filename,
        'contribution_id': attachment.contribution.id if attachment.contribution else None,
        'attachment_id': attachment.id,
        'file_id': attachment.file.id,
        'page': page_num  # if applicable
    }
```

---

## Next Steps

1. **Implement CitationBuilder** in `services/chat/citations.py`
2. **Update NL2SQL Pipeline** to return `source_event_ids`
3. **Update Document Indexing** to capture `contribution_id` and `file_id`
4. **Integrate into ChatService** citation generation flow
5. **Add Tests** for all citation patterns
6. **Update API Docs** with citation examples

For detailed implementation tasks, see: [tasks.md](tasks.md) (generated by `/speckit.tasks`)
