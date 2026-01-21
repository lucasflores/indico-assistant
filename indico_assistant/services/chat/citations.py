"""Citation formatting utilities for chat responses.

This module provides Pydantic models and utilities for generating source citations
in chat responses. Citations link back to event pages or document attachments.

Feature: 015-chat-source-citations
"""

from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator, model_validator


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
    event_id: int = Field(description="Indico event ID")
    contribution_id: int | None = Field(
        default=None, description="Contribution ID (only for documents)"
    )
    attachment_id: int | None = Field(
        default=None, description="Attachment ID (only for documents)"
    )
    file_id: int | None = Field(default=None, description="File ID (only for documents)")
    filename: str | None = Field(
        default=None, description="Original filename (only for documents)"
    )
    url: str = Field(description="Fully constructed citation URL")
    description: str = Field(description="Human-readable source descriptor")

    model_config = {"frozen": True}  # Immutable after creation

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL is valid HTTP/HTTPS."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @model_validator(mode='after')
    def validate_document_fields(self) -> 'SourceCitation':
        """Ensure document citations have required fields."""
        if self.type == "document":
            required = {
                "contribution_id": self.contribution_id,
                "attachment_id": self.attachment_id,
                "file_id": self.file_id,
                "filename": self.filename
            }
            for field, value in required.items():
                if value is None:
                    raise ValueError(f"{field} required for document citations")
        return self


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
        min_length=1, description="Response text with embedded markdown [source](url) links"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score (0.0-1.0)"
    )
    citations: list[SourceCitation] = Field(
        default_factory=list, description="Structured citation metadata for validation"
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is between 0.0 and 1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, v: str) -> str:
        """Ensure answer is not empty."""
        if not v.strip():
            raise ValueError("answer cannot be empty")
        return v


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
        self.base_url = base_url.rstrip("/")

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
        filename: str,
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
        filename: str,
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
