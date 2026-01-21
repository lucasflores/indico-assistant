"""Unit tests for citation generation utilities.

Feature: 015-chat-source-citations
Tasks: T007-T009, T017-T019, T037-T038
"""

import pytest
from pydantic import ValidationError

from indico_assistant.services.chat.citations import (
    CitationBuilder,
    ResponseWithCitations,
    SourceCitation,
)


class TestCitationBuilder:
    """Tests for CitationBuilder URL construction."""

    def test_build_event_url(self):
        """Test event URL construction (T007)."""
        builder = CitationBuilder(base_url="http://localhost:8000")
        url = builder.build_event_url(event_id=7)
        
        assert url == "http://localhost:8000/event/7/"
        assert url.startswith("http://")
        assert url.endswith("/")

    def test_build_event_url_strips_trailing_slash(self):
        """Test base URL trailing slash handling."""
        builder = CitationBuilder(base_url="http://localhost:8000/")
        url = builder.build_event_url(event_id=7)
        
        assert url == "http://localhost:8000/event/7/"
        # Should not have double slash
        assert "//" not in url[7:]  # Skip http://

    def test_build_event_citation(self):
        """Test event citation markdown formatting (T008)."""
        builder = CitationBuilder(base_url="http://localhost:8000")
        citation = builder.build_event_citation(event_id=7)
        
        assert citation == "[source](http://localhost:8000/event/7/)"
        assert citation.startswith("[source](")
        assert citation.endswith(")")

    def test_build_document_url_basic(self):
        """Test document URL construction (T017)."""
        builder = CitationBuilder(base_url="http://localhost:8000")
        url = builder.build_document_url(
            event_id=7,
            contribution_id=3,
            attachment_id=4,
            file_id=6,
            filename="paper.pdf"
        )
        
        expected = "http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf"
        assert url == expected

    def test_build_document_url_with_spaces(self):
        """Test filename URL encoding (T017)."""
        builder = CitationBuilder(base_url="http://localhost:8000")
        url = builder.build_document_url(
            event_id=7,
            contribution_id=3,
            attachment_id=4,
            file_id=6,
            filename="my paper.pdf"
        )
        
        assert "my%20paper.pdf" in url
        assert " " not in url

    def test_build_document_url_with_special_chars(self):
        """Test special character encoding."""
        builder = CitationBuilder(base_url="http://localhost:8000")
        url = builder.build_document_url(
            event_id=7,
            contribution_id=3,
            attachment_id=4,
            file_id=6,
            filename="résumé & notes.pdf"
        )
        
        assert "&" not in url or "%26" in url
        assert url.startswith("http://localhost:8000/event/7/")

    def test_build_document_citation(self):
        """Test document citation markdown formatting (T018)."""
        builder = CitationBuilder(base_url="http://localhost:8000")
        citation = builder.build_document_citation(
            event_id=7,
            contribution_id=3,
            attachment_id=4,
            file_id=6,
            filename="paper.pdf"
        )
        
        assert citation.startswith("[source](")
        assert citation.endswith(")")
        assert "paper.pdf" in citation


class TestSourceCitation:
    """Tests for SourceCitation Pydantic model."""

    def test_event_citation_valid(self):
        """Test valid event citation creation (T009)."""
        cite = SourceCitation(
            type="event",
            event_id=7,
            url="http://localhost:8000/event/7/",
            description="Event: Workshop 2024"
        )
        
        assert cite.type == "event"
        assert cite.event_id == 7
        assert cite.contribution_id is None
        assert cite.url == "http://localhost:8000/event/7/"

    def test_document_citation_valid(self):
        """Test valid document citation creation (T019)."""
        cite = SourceCitation(
            type="document",
            event_id=7,
            contribution_id=3,
            attachment_id=4,
            file_id=6,
            filename="paper.pdf",
            url="http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf",
            description="Document: paper.pdf"
        )
        
        assert cite.type == "document"
        assert cite.contribution_id == 3
        assert cite.attachment_id == 4
        assert cite.file_id == 6
        assert cite.filename == "paper.pdf"

    def test_document_citation_missing_fields(self):
        """Test document citation validation requires all fields (T019)."""
        with pytest.raises(ValidationError) as exc_info:
            SourceCitation(
                type="document",
                event_id=7,
                # Missing: contribution_id, attachment_id, file_id, filename
                url="http://localhost:8000/event/7/document.pdf",
                description="Document"
            )
        
        assert "contribution_id" in str(exc_info.value)

    def test_invalid_url_scheme(self):
        """Test URL validation rejects invalid schemes."""
        with pytest.raises(ValidationError) as exc_info:
            SourceCitation(
                type="event",
                event_id=7,
                url="ftp://localhost/event/7/",  # Invalid scheme
                description="Event"
            )
        
        assert "http" in str(exc_info.value).lower()

    def test_citation_immutable(self):
        """Test SourceCitation is immutable (frozen)."""
        cite = SourceCitation(
            type="event",
            event_id=7,
            url="http://localhost:8000/event/7/",
            description="Event"
        )
        
        with pytest.raises(ValidationError):
            cite.event_id = 8  # Should raise error


class TestResponseWithCitations:
    """Tests for ResponseWithCitations model."""

    def test_response_with_citations_valid(self):
        """Test valid response creation."""
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
        assert "[source]" in response.answer

    def test_response_empty_citations(self):
        """Test response with no citations (general knowledge)."""
        response = ResponseWithCitations(
            answer="Machine learning is a field of AI.",
            confidence=0.95,
            citations=[]
        )
        
        assert len(response.citations) == 0
        assert response.confidence == 0.95

    def test_confidence_validation(self):
        """Test confidence must be between 0 and 1."""
        with pytest.raises(ValidationError):
            ResponseWithCitations(
                answer="Test",
                confidence=1.5,  # Invalid
                citations=[]
            )

    def test_empty_answer_rejected(self):
        """Test empty answer is rejected."""
        with pytest.raises(ValidationError):
            ResponseWithCitations(
                answer="",  # Invalid
                confidence=0.9,
                citations=[]
            )
