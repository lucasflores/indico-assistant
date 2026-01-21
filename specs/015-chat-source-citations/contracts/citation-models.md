# Python API Contract: Citation Models

**Feature**: 015-chat-source-citations  
**Module**: `indico_assistant.services.chat.citations`  
**Date**: 2026-01-20

## SourceCitation

Pydantic model representing a single source citation.

### Schema

```python
from pydantic import BaseModel, Field, HttpUrl
from typing import Literal

class SourceCitation(BaseModel):
    """A single source citation with URL and metadata.
    
    Attributes:
        type: Source type ('event' or 'document')
        event_id: Indico event ID
        contribution_id: Contribution ID (documents only)
        attachment_id: Attachment ID (documents only)
        file_id: File ID (documents only)
        filename: Original filename (documents only)
        url: Fully constructed citation URL
        description: Human-readable source descriptor
    
    Example:
        >>> # Event citation
        >>> cite = SourceCitation(
        ...     type="event",
        ...     event_id=7,
        ...     url="http://localhost:8000/event/7/",
        ...     description="Event: ICHEP 2024"
        ... )
        
        >>> # Document citation
        >>> cite = SourceCitation(
        ...     type="document",
        ...     event_id=7,
        ...     contribution_id=3,
        ...     attachment_id=4,
        ...     file_id=6,
        ...     filename="paper.pdf",
        ...     url="http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf",
        ...     description="Document: paper.pdf"
        ... )
    """
    type: Literal["event", "document"] = Field(
        description="Source type for proper URL formatting"
    )
    event_id: int = Field(
        description="Indico event ID"
    )
    contribution_id: int | None = Field(
        default=None,
        description="Contribution ID (only for documents)"
    )
    attachment_id: int | None = Field(
        default=None,
        description="Attachment ID (only for documents)"
    )
    file_id: int | None = Field(
        default=None,
        description="File ID (only for documents)"
    )
    filename: str | None = Field(
        default=None,
        description="Original filename (only for documents)"
    )
    url: str = Field(
        description="Fully constructed citation URL"
    )
    description: str = Field(
        description="Human-readable source descriptor"
    )
    
    model_config = {"frozen": True}  # Immutable after creation
```

### Validation

```python
from pydantic import field_validator, ValidationError

class SourceCitation(BaseModel):
    # ... fields ...
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL is valid HTTP/HTTPS."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v
    
    @field_validator('type')
    @classmethod
    def validate_document_fields(cls, v: str, info) -> str:
        """Ensure document citations have required fields."""
        if v == 'document':
            required = ['contribution_id', 'attachment_id', 'file_id', 'filename']
            for field in required:
                if info.data.get(field) is None:
                    raise ValueError(f'{field} required for document citations')
        return v
```

### Usage

```python
# Creating event citation
event_cite = SourceCitation(
    type="event",
    event_id=7,
    url="http://localhost:8000/event/7/",
    description="Event: Workshop 2024"
)

# Creating document citation
doc_cite = SourceCitation(
    type="document",
    event_id=7,
    contribution_id=3,
    attachment_id=4,
    file_id=6,
    filename="slides.pdf",
    url="http://localhost:8000/event/7/contributions/3/attachments/4/6/slides.pdf",
    description="Document: slides.pdf"
)

# Serialization
event_cite.model_dump()  # Returns dict
event_cite.model_dump_json()  # Returns JSON string
```

---

## ResponseWithCitations

LLM response model with embedded citations.

### Schema

```python
from pydantic import BaseModel, Field

class ResponseWithCitations(BaseModel):
    """LLM response with inline source citations.
    
    Attributes:
        answer: Response text with embedded [source](url) markdown links
        confidence: Confidence score (0.0-1.0)
        citations: Structured citation metadata for validation
    
    Example:
        >>> response = ResponseWithCitations(
        ...     answer="The workshop is on January 25th ([source](http://localhost:8000/event/7/))",
        ...     confidence=0.92,
        ...     citations=[
        ...         SourceCitation(
        ...             type="event",
        ...             event_id=7,
        ...             url="http://localhost:8000/event/7/",
        ...             description="Event: Workshop 2024"
        ...         )
        ...     ]
        ... )
    """
    answer: str = Field(
        min_length=1,
        description="Response text with embedded markdown [source](url) links"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0)"
    )
    citations: list[SourceCitation] = Field(
        default_factory=list,
        description="Structured citation metadata for validation"
    )
```

### Validation

```python
from pydantic import field_validator

class ResponseWithCitations(BaseModel):
    # ... fields ...
    
    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is between 0.0 and 1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('confidence must be between 0.0 and 1.0')
        return v
    
    @field_validator('answer')
    @classmethod
    def validate_answer(cls, v: str) -> str:
        """Ensure answer is not empty."""
        if not v.strip():
            raise ValueError('answer cannot be empty')
        return v
```

### Usage

```python
# Creating response with citations
response = ResponseWithCitations(
    answer="The paper ([source](http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf)) shows that...",
    confidence=0.88,
    citations=[
        SourceCitation(
            type="document",
            event_id=7,
            contribution_id=3,
            attachment_id=4,
            file_id=6,
            filename="paper.pdf",
            url="http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf",
            description="Document: paper.pdf"
        )
    ]
)

# Access fields
print(response.answer)
print(f"Confidence: {response.confidence}")
for cite in response.citations:
    print(f"- {cite.description}: {cite.url}")
```

---

## CitationBuilder

Service class for constructing citation URLs and markdown links.

### Class Definition

```python
from urllib.parse import quote

class CitationBuilder:
    """Utility for constructing source citation URLs.
    
    Handles URL encoding and markdown link formatting for both
    event and document citations.
    
    Attributes:
        base_url: Indico base URL (e.g., 'http://localhost:8000')
    
    Example:
        >>> builder = CitationBuilder(base_url="http://localhost:8000")
        >>> builder.build_event_citation(7)
        '[source](http://localhost:8000/event/7/)'
    """
    
    def __init__(self, base_url: str) -> None:
        """Initialize citation builder.
        
        Args:
            base_url: Indico base URL without trailing slash
        """
        self.base_url = base_url.rstrip('/')
    
    def build_event_url(self, event_id: int) -> str:
        """Construct event page URL.
        
        Args:
            event_id: Indico event ID
            
        Returns:
            Full event URL
        """
        return f"{self.base_url}/event/{event_id}/"
    
    def build_event_citation(self, event_id: int) -> str:
        """Build markdown citation link for event.
        
        Args:
            event_id: Indico event ID
            
        Returns:
            Markdown link: [source](url)
        """
        url = self.build_event_url(event_id)
        return f"[source]({url})"
    
    def build_document_url(
        self,
        event_id: int,
        contribution_id: int,
        attachment_id: int,
        file_id: int,
        filename: str
    ) -> str:
        """Construct attachment download URL.
        
        Args:
            event_id: Indico event ID
            contribution_id: Contribution ID
            attachment_id: Attachment ID
            file_id: File ID
            filename: Original filename (will be URL-encoded)
            
        Returns:
            Full attachment URL
        """
        safe_filename = quote(filename)
        return (
            f"{self.base_url}/event/{event_id}/"
            f"contributions/{contribution_id}/"
            f"attachments/{attachment_id}/{file_id}/{safe_filename}"
        )
    
    def build_document_citation(
        self,
        event_id: int,
        contribution_id: int,
        attachment_id: int,
        file_id: int,
        filename: str
    ) -> str:
        """Build markdown citation link for document.
        
        Args:
            event_id: Indico event ID
            contribution_id: Contribution ID
            attachment_id: Attachment ID
            file_id: File ID
            filename: Original filename
            
        Returns:
            Markdown link: [source](url)
        """
        url = self.build_document_url(
            event_id, contribution_id, attachment_id, file_id, filename
        )
        return f"[source]({url})"
```

### Usage Examples

```python
# Initialize builder
builder = CitationBuilder(base_url="http://localhost:8000")

# Build event citation
event_cite = builder.build_event_citation(event_id=7)
# Returns: "[source](http://localhost:8000/event/7/)"

# Build document citation
doc_cite = builder.build_document_citation(
    event_id=7,
    contribution_id=3,
    attachment_id=4,
    file_id=6,
    filename="research paper.pdf"
)
# Returns: "[source](http://localhost:8000/event/7/contributions/3/attachments/4/6/research%20paper.pdf)"

# Build URLs without markdown
event_url = builder.build_event_url(7)
# Returns: "http://localhost:8000/event/7/"

doc_url = builder.build_document_url(7, 3, 4, 6, "slides.pdf")
# Returns: "http://localhost:8000/event/7/contributions/3/attachments/4/6/slides.pdf"
```

---

## Testing Contracts

### Unit Test Examples

```python
import pytest
from pydantic import ValidationError
from indico_assistant.services.chat.citations import (
    SourceCitation,
    ResponseWithCitations,
    CitationBuilder
)

def test_source_citation_event():
    """Test event citation creation."""
    cite = SourceCitation(
        type="event",
        event_id=7,
        url="http://localhost:8000/event/7/",
        description="Event: Workshop"
    )
    assert cite.type == "event"
    assert cite.event_id == 7
    assert cite.url == "http://localhost:8000/event/7/"

def test_source_citation_document_validation():
    """Test document citation requires all fields."""
    with pytest.raises(ValidationError):
        SourceCitation(
            type="document",
            event_id=7,
            url="http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf",
            description="Document: paper.pdf"
            # Missing: contribution_id, attachment_id, file_id, filename
        )

def test_response_with_citations():
    """Test response model with citations."""
    response = ResponseWithCitations(
        answer="The workshop ([source](http://localhost:8000/event/7/)) is on Jan 25th",
        confidence=0.9,
        citations=[
            SourceCitation(
                type="event",
                event_id=7,
                url="http://localhost:8000/event/7/",
                description="Event: Workshop"
            )
        ]
    )
    assert len(response.citations) == 1
    assert response.confidence == 0.9

def test_citation_builder_event():
    """Test event URL construction."""
    builder = CitationBuilder("http://localhost:8000")
    url = builder.build_event_url(7)
    assert url == "http://localhost:8000/event/7/"
    
    cite = builder.build_event_citation(7)
    assert cite == "[source](http://localhost:8000/event/7/)"

def test_citation_builder_document_encoding():
    """Test filename URL encoding."""
    builder = CitationBuilder("http://localhost:8000")
    url = builder.build_document_url(7, 3, 4, 6, "my paper.pdf")
    assert "my%20paper.pdf" in url
    assert url.startswith("http://localhost:8000/event/7/")
```
