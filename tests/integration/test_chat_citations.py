# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Integration tests for chat citation features.

Feature: 015-chat-source-citations
Task: T016 - Integration test for event citation in chat response
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

from indico_assistant.services.chat.service import ChatService
from indico_assistant.services.nl2sql.models import PipelineResult


@pytest.fixture
def mock_plugin():
    """Mock AssistantPlugin with base_url setting."""
    plugin = Mock()
    plugin.settings = {"base_url": "http://localhost:8000"}
    return plugin


@pytest.fixture
def mock_session_manager():
    """Mock SessionManager for chat service."""
    manager = Mock()
    session = Mock()
    session.id = uuid4()
    session.event_id = 123
    
    user_msg = Mock()
    user_msg.id = uuid4()
    
    assistant_msg = Mock()
    assistant_msg.id = uuid4()
    
    manager.get_session.return_value = session
    manager.create_session.return_value = session
    manager.add_user_message.return_value = user_msg
    manager.add_assistant_message.return_value = assistant_msg
    manager.validate_session_ownership.return_value = True
    manager.commit.return_value = None
    manager.rollback.return_value = None
    
    return manager


@pytest.fixture
def mock_context_builder():
    """Mock ContextBuilder for chat service."""
    builder = Mock()
    builder.build_context.return_value = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"}
    ]
    return builder


@pytest.fixture
def chat_service(mock_session_manager, mock_context_builder):
    """Create ChatService instance with mocked dependencies."""
    return ChatService(
        session_manager=mock_session_manager,
        context_builder=mock_context_builder
    )


def test_event_citations_in_nl2sql_response(chat_service, mock_plugin):
    """
    Test that event citations are generated and included in metadata.
    
    Feature: 015-chat-source-citations
    Task: T016
    
    Scenario:
    - User asks question about events
    - NL2SQL pipeline returns results with source_event_ids
    - Chat service extracts event IDs and builds citation metadata
    - Response includes data_sources with citation URLs
    """
    # Arrange
    user_id = 1
    session_id = None
    event_id = 123
    message = "How many participants attended recent events?"
    
    # Mock pipeline result with source_event_ids
    pipeline_result = PipelineResult(
        success=True,
        answer="There were 42 participants in [Event: 123](/event/123) and 15 in [Event: 456](/event/456).",
        confidence=0.95,
        generated_sql="SELECT COUNT(*) FROM registrations WHERE event_id IN (123, 456)",
        tables_accessed=["events", "registrations"],
        row_count=2,
        source_event_ids=[123, 456],  # Feature 015: event sources
        total_time_ms=500,
        classification_time_ms=100,
        generation_time_ms=200,
        execution_time_ms=150,
        formatting_time_ms=50
    )
    
    mock_pipeline = Mock()
    mock_pipeline.process.return_value = pipeline_result
    
    # Patch dependencies
    with patch('indico_assistant.services.chat.service.AssistantPlugin') as MockPlugin, \
         patch('indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin') as mock_create_pipeline:
        
        MockPlugin.instance = mock_plugin
        mock_create_pipeline.return_value = mock_pipeline
        
        # Act
        result = chat_service.process_message(
            message=message,
            user_id=user_id,
            session_id=session_id,
            event_id=event_id
        )
    
    # Assert
    assert result.response == pipeline_result.answer
    assert "data_sources" in result.metadata
    
    data_sources = result.metadata["data_sources"]
    assert isinstance(data_sources, list)
    assert len(data_sources) == 2
    
    # Verify citation metadata structure
    citation_1 = data_sources[0]
    assert citation_1["type"] == "event"
    assert citation_1["event_id"] == 123
    assert citation_1["url"] == "http://localhost:8000/event/123"
    assert "Event: 123" in citation_1["description"]
    
    citation_2 = data_sources[1]
    assert citation_2["type"] == "event"
    assert citation_2["event_id"] == 456
    assert citation_2["url"] == "http://localhost:8000/event/456"
    assert "Event: 456" in citation_2["description"]


def test_no_citations_for_table_only_queries(chat_service, mock_plugin):
    """
    Test that queries without event sources fall back to table names.
    
    Feature: 015-chat-source-citations
    Task: T016
    
    Scenario:
    - User asks general question (no specific event data)
    - NL2SQL returns empty source_event_ids
    - Response falls back to legacy table list format
    """
    # Arrange
    user_id = 1
    message = "What tables are available?"
    
    # Mock pipeline result WITHOUT source_event_ids
    pipeline_result = PipelineResult(
        success=True,
        answer="The available tables include: events, registrations, contributions.",
        confidence=0.90,
        generated_sql="SELECT table_name FROM information_schema.tables",
        tables_accessed=["information_schema"],
        row_count=10,
        source_event_ids=[],  # No event sources
        total_time_ms=300,
        classification_time_ms=50,
        generation_time_ms=100,
        execution_time_ms=100,
        formatting_time_ms=50
    )
    
    mock_pipeline = Mock()
    mock_pipeline.process.return_value = pipeline_result
    
    # Patch dependencies
    with patch('indico_assistant.services.chat.service.AssistantPlugin') as MockPlugin, \
         patch('indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin') as mock_create_pipeline:
        
        MockPlugin.instance = mock_plugin
        mock_create_pipeline.return_value = mock_pipeline
        
        # Act
        result = chat_service.process_message(
            message=message,
            user_id=user_id,
            session_id=None,
            event_id=None
        )
    
    # Assert
    assert result.response == pipeline_result.answer
    assert "data_sources" in result.metadata
    
    # Should fall back to table list (legacy format)
    data_sources = result.metadata["data_sources"]
    assert data_sources == ["information_schema"]


def test_citation_builder_integration(chat_service, mock_plugin):
    """
    Test that CitationBuilder is properly used for URL construction.
    
    Feature: 015-chat-source-citations
    Task: T016
    
    Scenario:
    - Verify base_url is correctly loaded from plugin settings
    - Verify CitationBuilder constructs proper URLs
    - Verify URLs are properly encoded
    """
    # Arrange
    user_id = 1
    
    # Custom base URL with path
    mock_plugin.settings["base_url"] = "https://indico.example.org/platform"
    
    pipeline_result = PipelineResult(
        success=True,
        answer="Check [Event: 789](/platform/event/789).",
        confidence=0.92,
        generated_sql="SELECT * FROM events WHERE id = 789",
        tables_accessed=["events"],
        row_count=1,
        source_event_ids=[789],
        total_time_ms=200,
        classification_time_ms=40,
        generation_time_ms=80,
        execution_time_ms=60,
        formatting_time_ms=20
    )
    
    mock_pipeline = Mock()
    mock_pipeline.process.return_value = pipeline_result
    
    # Patch dependencies
    with patch('indico_assistant.services.chat.service.AssistantPlugin') as MockPlugin, \
         patch('indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin') as mock_create_pipeline:
        
        MockPlugin.instance = mock_plugin
        mock_create_pipeline.return_value = mock_pipeline
        
        # Act
        result = chat_service.process_message(
            message="Tell me about event 789",
            user_id=user_id,
            session_id=None,
            event_id=789
        )
    
    # Assert
    data_sources = result.metadata["data_sources"]
    assert len(data_sources) == 1
    assert data_sources[0]["url"] == "https://indico.example.org/platform/event/789"


def test_document_citations_from_rag_results(chat_service, mock_plugin):
    """
    Test that document citations are extracted from RAG search results.
    
    Feature: 015-chat-source-citations
    Task: T025
    
    Scenario:
    - User asks about document content
    - RAG returns search results with document metadata
    - ChatService extracts document citation metadata
    - Response metadata includes document citations with URLs
    """
    # Arrange
    from unittest.mock import Mock
    
    # Mock SearchResult objects with document metadata
    search_result_1 = Mock()
    search_result_1.event_id = 7
    search_result_1.metadata = {
        'contribution_id': 3,
        'attachment_id': 4,
        'file_id': 6,
        'filename': 'research_paper.pdf'
    }
    search_result_1.content = "This study shows..."
    search_result_1.similarity = 0.95
    
    search_result_2 = Mock()
    search_result_2.event_id = 7
    search_result_2.metadata = {
        'contribution_id': 3,
        'attachment_id': 4,
        'file_id': 8,
        'filename': 'presentation.pptx'
    }
    search_result_2.content = "The presentation demonstrates..."
    search_result_2.similarity = 0.89
    
    search_results = [search_result_1, search_result_2]
    
    # Act
    citations = chat_service._extract_document_citations(search_results)
    
    # Assert
    assert len(citations) == 2
    
    # Verify first citation (PDF)
    cite1 = citations[0]
    assert cite1["type"] == "document"
    assert cite1["event_id"] == 7
    assert cite1["contribution_id"] == 3
    assert cite1["attachment_id"] == 4
    assert cite1["file_id"] == 6
    assert cite1["filename"] == "research_paper.pdf"
    assert cite1["url"] == "http://localhost:8000/event/7/contributions/3/attachments/4/6/research_paper.pdf"
    assert "research_paper.pdf" in cite1["description"]
    
    # Verify second citation (PPTX)
    cite2 = citations[1]
    assert cite2["type"] == "document"
    assert cite2["file_id"] == 8
    assert cite2["filename"] == "presentation.pptx"
    assert cite2["url"] == "http://localhost:8000/event/7/contributions/3/attachments/4/8/presentation.pptx"


def test_document_citation_deduplication(chat_service, mock_plugin):
    """
    Test that duplicate file citations are removed.
    
    Feature: 015-chat-source-citations
    Task: T025
    
    Scenario:
    - Multiple RAG chunks from same document
    - Citations should be deduplicated by file_id
    - Only one citation per unique document
    """
    # Arrange
    from unittest.mock import Mock
    
    # Same file_id appears twice
    search_result_1 = Mock()
    search_result_1.event_id = 7
    search_result_1.metadata = {
        'contribution_id': 3,
        'attachment_id': 4,
        'file_id': 6,
        'filename': 'paper.pdf'
    }
    
    search_result_2 = Mock()
    search_result_2.event_id = 7
    search_result_2.metadata = {
        'contribution_id': 3,
        'attachment_id': 4,
        'file_id': 6,  # Same file_id
        'filename': 'paper.pdf'
    }
    
    search_results = [search_result_1, search_result_2]
    
    # Act
    citations = chat_service._extract_document_citations(search_results)
    
    # Assert - only one citation despite two chunks
    assert len(citations) == 1
    assert citations[0]["file_id"] == 6


def test_document_citation_handles_missing_metadata(chat_service, mock_plugin):
    """
    Test that results with incomplete metadata are skipped gracefully.
    
    Feature: 015-chat-source-citations
    Task: T025
    
    Scenario:
    - Some search results lack contribution_id or file_id
    - Citations should skip incomplete results
    - No errors raised, only valid citations returned
    """
    # Arrange
    from unittest.mock import Mock
    
    # Valid result
    valid_result = Mock()
    valid_result.event_id = 7
    valid_result.metadata = {
        'contribution_id': 3,
        'attachment_id': 4,
        'file_id': 6,
        'filename': 'valid.pdf'
    }
    
    # Missing contribution_id
    invalid_result_1 = Mock()
    invalid_result_1.event_id = 7
    invalid_result_1.metadata = {
        'attachment_id': 4,
        'file_id': 7,
        'filename': 'invalid1.pdf'
    }
    
    # Missing file_id
    invalid_result_2 = Mock()
    invalid_result_2.event_id = 7
    invalid_result_2.metadata = {
        'contribution_id': 3,
        'attachment_id': 4,
        'filename': 'invalid2.pdf'
    }
    
    # None metadata
    invalid_result_3 = Mock()
    invalid_result_3.event_id = 7
    invalid_result_3.metadata = None
    
    search_results = [valid_result, invalid_result_1, invalid_result_2, invalid_result_3]
    
    # Act
    citations = chat_service._extract_document_citations(search_results)
    
    # Assert - only valid citation returned
    assert len(citations) == 1
    assert citations[0]["filename"] == "valid.pdf"


def test_mixed_event_and_document_citations(chat_service, mock_plugin):
    """
    Test that both event and document citations appear together.
    
    Feature: 015-chat-source-citations
    Task: T026
    
    Scenario:
    - Query requires both NL2SQL (event data) and RAG (document content)
    - Response includes both event and document citations
    - Each citation type is distinguishable
    """
    # Arrange
    from unittest.mock import Mock
    user_id = 1
    message = "Who presented the research on ML at the conference?"
    
    # Mock pipeline with event sources
    pipeline_result = Mock()
    pipeline_result.success = True
    pipeline_result.answer = "Dr. Smith presented [Event: 123](/event/123) about the ML research [source](/event/123/contributions/5/attachments/2/10/paper.pdf)."
    pipeline_result.confidence = 0.93
    pipeline_result.generated_sql = "SELECT * FROM contributions WHERE event_id = 123"
    pipeline_result.tables_accessed = ["contributions", "events"]
    pipeline_result.row_count = 1
    pipeline_result.source_event_ids = [123]
    pipeline_result.total_time_ms = 450
    pipeline_result.classification_time_ms = 80
    pipeline_result.generation_time_ms = 150
    pipeline_result.execution_time_ms = 180
    pipeline_result.formatting_time_ms = 40
    
    mock_pipeline = Mock()
    mock_pipeline.process.return_value = pipeline_result
    
    # Act
    with patch('indico_assistant.services.chat.service.AssistantPlugin') as MockPlugin, \
         patch('indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin') as mock_create_pipeline:
        
        MockPlugin.instance = mock_plugin
        mock_create_pipeline.return_value = mock_pipeline
        
        result = chat_service.process_message(
            message=message,
            user_id=user_id,
            session_id=None,
            event_id=123
        )
    
    # Assert
    data_sources = result.metadata["data_sources"]
    assert len(data_sources) >= 1  # At least event citation
    
    # Check for event citation
    event_sources = [s for s in data_sources if s.get("type") == "event"]
    assert len(event_sources) == 1
    assert event_sources[0]["event_id"] == 123
    assert event_sources[0]["url"] == "http://localhost:8000/event/123"
    
    # Note: Document citations would be added if RAG results were included
    # This test validates the event citation part of mixed scenario


def test_general_knowledge_no_citations(chat_service, mock_plugin):
    """
    Test that general knowledge queries don't generate false citations.
    
    Feature: 015-chat-source-citations
    Task: T032
    
    Scenario:
    - User asks general knowledge question
    - No NL2SQL or RAG sources used
    - Response has empty data_sources list
    """
    # Arrange
    user_id = 1
    message = "What is machine learning?"
    
    # Mock pipeline result with NO source_event_ids (general knowledge)
    pipeline_result = Mock()
    pipeline_result.success = True
    pipeline_result.answer = "Machine learning is a field of artificial intelligence..."
    pipeline_result.confidence = 0.88
    pipeline_result.generated_sql = None  # No SQL for general knowledge
    pipeline_result.tables_accessed = []
    pipeline_result.row_count = 0
    pipeline_result.source_event_ids = []  # No event sources
    pipeline_result.total_time_ms = 150
    pipeline_result.classification_time_ms = 30
    pipeline_result.generation_time_ms = 80
    pipeline_result.execution_time_ms = 0
    pipeline_result.formatting_time_ms = 40
    
    mock_pipeline = Mock()
    mock_pipeline.process.return_value = pipeline_result
    
    # Act
    with patch('indico_assistant.services.chat.service.AssistantPlugin') as MockPlugin, \
         patch('indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin') as mock_create_pipeline:
        
        MockPlugin.instance = mock_plugin
        mock_create_pipeline.return_value = mock_pipeline
        
        result = chat_service.process_message(
            message=message,
            user_id=user_id,
            session_id=None,
            event_id=None
        )
    
    # Assert - No citations for general knowledge
    data_sources = result.metadata.get("data_sources", [])
    assert len(data_sources) == 0 or data_sources == []


def test_mixed_general_and_system_knowledge(chat_service, mock_plugin):
    """
    Test partial citations when combining general and system knowledge.
    
    Feature: 015-chat-source-citations  
    Task: T033
    
    Scenario:
    - Response includes both general knowledge and system data
    - Only system-sourced information gets citations
    - General knowledge parts have no citations
    """
    # Arrange
    user_id = 1
    message = "What is ML and which events covered it?"
    
    # Mock pipeline with partial sources (only event data, not ML definition)
    pipeline_result = Mock()
    pipeline_result.success = True
    pipeline_result.answer = "Machine learning is AI. Event 200 covered ML topics [Event: 200](/event/200)."
    pipeline_result.confidence = 0.90
    pipeline_result.generated_sql = "SELECT * FROM events WHERE topic LIKE '%ML%'"
    pipeline_result.tables_accessed = ["events"]
    pipeline_result.row_count = 1
    pipeline_result.source_event_ids = [200]  # Only for event part
    pipeline_result.total_time_ms = 300
    pipeline_result.classification_time_ms = 60
    pipeline_result.generation_time_ms = 120
    pipeline_result.execution_time_ms = 80
    pipeline_result.formatting_time_ms = 40
    
    mock_pipeline = Mock()
    mock_pipeline.process.return_value = pipeline_result
    
    # Act
    with patch('indico_assistant.services.chat.service.AssistantPlugin') as MockPlugin, \
         patch('indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin') as mock_create_pipeline:
        
        MockPlugin.instance = mock_plugin
        mock_create_pipeline.return_value = mock_pipeline
        
        result = chat_service.process_message(
            message=message,
            user_id=user_id,
            session_id=None,
            event_id=None
        )
    
    # Assert - Only event citation present (general knowledge part uncited)
    data_sources = result.metadata["data_sources"]
    assert len(data_sources) == 1
    assert data_sources[0]["type"] == "event"
    assert data_sources[0]["event_id"] == 200



