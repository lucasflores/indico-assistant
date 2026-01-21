"""Contract tests for citation models.

Validates that Pydantic models conform to the documented API contracts.

Feature: 015-chat-source-citations
Tasks: T009, T019, T027, T028
"""

import pytest
from pydantic import ValidationError

from indico_assistant.services.chat.citations import (
    ResponseWithCitations,
    SourceCitation,
)


class TestSourceCitationContract:
    """Contract tests for SourceCitation model."""

    def test_event_citation_contract(self):
        """Test event citation matches contract (T009)."""
        cite = SourceCitation(
            type="event",
            event_id=123,
            url="https://example.com/event/123/",
            description="Event: Annual Conference"
        )
        
        # Contract: type is Literal["event", "document"]
        assert cite.type in ["event", "document"]
        
        # Contract: event_id is int
        assert isinstance(cite.event_id, int)
        
        # Contract: url is str starting with http/https
        assert isinstance(cite.url, str)
        assert cite.url.startswith(("http://", "https://"))
        
        # Contract: description is str
        assert isinstance(cite.description, str)
        
        # Contract: Optional fields are None for event type
        assert cite.contribution_id is None
        assert cite.attachment_id is None
        assert cite.file_id is None
        assert cite.filename is None

    def test_document_citation_contract(self):
        """Test document citation matches contract (T019)."""
        cite = SourceCitation(
            type="document",
            event_id=123,
            contribution_id=456,
            attachment_id=789,
            file_id=101,
            filename="document.pdf",
            url="https://example.com/event/123/contributions/456/attachments/789/101/document.pdf",
            description="Document: document.pdf"
        )
        
        # Contract: All document fields required
        assert isinstance(cite.contribution_id, int)
        assert isinstance(cite.attachment_id, int)
        assert isinstance(cite.file_id, int)
        assert isinstance(cite.filename, str)
        
        # Contract: URL contains all path components
        assert "/event/123/" in cite.url
        assert "/contributions/456/" in cite.url
        assert "/attachments/789/" in cite.url
        assert "/101/" in cite.url
        assert "document.pdf" in cite.url

    def test_citation_serialization_contract(self):
        """Test citation can be serialized to dict/JSON."""
        cite = SourceCitation(
            type="event",
            event_id=7,
            url="http://localhost:8000/event/7/",
            description="Event"
        )
        
        # Contract: model_dump() returns dict
        data = cite.model_dump()
        assert isinstance(data, dict)
        assert data["type"] == "event"
        assert data["event_id"] == 7
        
        # Contract: model_dump_json() returns JSON string
        json_str = cite.model_dump_json()
        assert isinstance(json_str, str)
        assert '"type":"event"' in json_str or '"type": "event"' in json_str


class TestResponseWithCitationsContract:
    """Contract tests for ResponseWithCitations model."""

    def test_response_structure_contract(self):
        """Test response structure matches contract (T028)."""
        response = ResponseWithCitations(
            answer="Test answer with citation",
            confidence=0.85,
            citations=[
                SourceCitation(
                    type="event",
                    event_id=7,
                    url="http://localhost:8000/event/7/",
                    description="Event"
                )
            ]
        )
        
        # Contract: answer is non-empty str
        assert isinstance(response.answer, str)
        assert len(response.answer) > 0
        
        # Contract: confidence is float between 0 and 1
        assert isinstance(response.confidence, float)
        assert 0.0 <= response.confidence <= 1.0
        
        # Contract: citations is list of SourceCitation
        assert isinstance(response.citations, list)
        assert all(isinstance(c, SourceCitation) for c in response.citations)

    def test_mixed_citation_types_contract(self):
        """Test response with multiple citation types (T027, T028)."""
        response = ResponseWithCitations(
            answer="Test answer",
            confidence=0.9,
            citations=[
                SourceCitation(
                    type="event",
                    event_id=7,
                    url="http://localhost:8000/event/7/",
                    description="Event: Conference"
                ),
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
        
        # Contract: Can mix event and document citations
        assert len(response.citations) == 2
        assert response.citations[0].type == "event"
        assert response.citations[1].type == "document"
        
        # Contract: Each citation type has proper fields
        event_cite = response.citations[0]
        assert event_cite.contribution_id is None
        
        doc_cite = response.citations[1]
        assert doc_cite.contribution_id is not None
        assert doc_cite.filename is not None

    def test_empty_citations_contract(self):
        """Test response with no citations is valid."""
        response = ResponseWithCitations(
            answer="General knowledge answer",
            confidence=0.95,
            citations=[]
        )
        
        # Contract: Empty citations list is valid
        assert isinstance(response.citations, list)
        assert len(response.citations) == 0

    def test_validation_contract(self):
        """Test validation rules are enforced."""
        # Contract: Empty answer rejected
        with pytest.raises(ValidationError):
            ResponseWithCitations(
                answer="",
                confidence=0.9,
                citations=[]
            )
        
        # Contract: Confidence out of range rejected
        with pytest.raises(ValidationError):
            ResponseWithCitations(
                answer="Test",
                confidence=1.5,
                citations=[]
            )
        
        with pytest.raises(ValidationError):
            ResponseWithCitations(
                answer="Test",
                confidence=-0.1,
                citations=[]
            )


class TestMixedCitationTypes:
    """
    Contract tests for mixed event and document citations.
    
    Feature: 015-chat-source-citations
    Task: T027
    """
    
    def test_heterogeneous_citation_list(self):
        """Test that citations list can contain mixed types."""
        # Arrange
        event_cite = SourceCitation(
            type="event",
            event_id=50,
            url="http://localhost:8000/event/50",
            description="Workshop Event"
        )
        
        doc_cite = SourceCitation(
            type="document",
            event_id=50,
            contribution_id=3,
            attachment_id=1,
            file_id=5,
            filename="slides.pdf",
            url="http://localhost:8000/event/50/contributions/3/attachments/1/5/slides.pdf",
            description="Presentation Slides"
        )
        
        # Act
        response = ResponseWithCitations(
            answer="The workshop [Event: 50](/event/50) included slides [slides.pdf](url).",
            confidence=0.92,
            citations=[event_cite, doc_cite]
        )
        
        # Assert
        assert len(response.citations) == 2
        assert response.citations[0].type == "event"
        assert response.citations[1].type == "document"
        
        # Type-specific fields
        assert response.citations[0].contribution_id is None  # Events don't have this
        assert response.citations[1].filename == "slides.pdf"  # Documents do
    
    def test_multiple_documents_single_event(self):
        """Test event with multiple document citations."""
        event_cite = SourceCitation(
            type="event",
            event_id=75,
            url="http://localhost:8000/event/75",
            description="Conference"
        )
        
        doc1 = SourceCitation(
            type="document",
            event_id=75,
            contribution_id=10,
            attachment_id=3,
            file_id=20,
            filename="paper1.pdf",
            url="http://localhost:8000/event/75/contributions/10/attachments/3/20/paper1.pdf",
            description="First Paper"
        )
        
        doc2 = SourceCitation(
            type="document",
            event_id=75,
            contribution_id=11,
            attachment_id=4,
            file_id=21,
            filename="paper2.pdf",
            url="http://localhost:8000/event/75/contributions/11/attachments/4/21/paper2.pdf",
            description="Second Paper"
        )
        
        # Act
        response = ResponseWithCitations(
            answer="Multiple papers were presented.",
            confidence=0.88,
            citations=[event_cite, doc1, doc2]
        )
        
        # Assert
        assert len(response.citations) == 3
        doc_cites = [c for c in response.citations if c.type == "document"]
        assert len(doc_cites) == 2
        assert all(c.event_id == 75 for c in doc_cites)
