# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Integration tests for user ID passthrough feature.

Feature: 016-user-id-passthrough
Task: T029, T030

These tests verify the end-to-end flow of:
1. Authenticated user making personal queries
2. Unauthenticated user being prompted for identity
3. Identity resolution from user-provided info
4. Session persistence of resolved identity
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestAuthenticatedUserFlow:
    """Test authenticated user making personal queries (T029)."""

    @patch('indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin')
    @patch('indico_assistant.plugin.AssistantPlugin')
    def test_authenticated_user_personal_query_includes_user_id(
        self, mock_plugin_class: MagicMock, mock_create_pipeline: MagicMock
    ) -> None:
        """Authenticated user's personal query should pass user_id to pipeline."""
        from indico_assistant.services.chat.service import ChatService
        from indico_assistant.services.chat.session_manager import SessionManager
        from indico_assistant.services.chat.context_builder import ContextBuilder
        
        # Setup mocks
        mock_plugin = MagicMock()
        mock_plugin_class.instance = mock_plugin
        
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.answer = "You have 3 meetings this week"
        mock_result.generated_sql = "SELECT * FROM events..."
        mock_result.confidence = 0.95
        mock_result.tables_accessed = []
        mock_result.error = None
        mock_pipeline.process.return_value = mock_result
        mock_create_pipeline.return_value = mock_pipeline
        
        # Mock session manager
        mock_session_manager = MagicMock(spec=SessionManager)
        mock_session = MagicMock()
        mock_session.id = uuid4()
        mock_session.event_id = None
        mock_session.resolved_user_id = None
        mock_session_manager.get_session_or_create.return_value = (mock_session, True)
        mock_session_manager.add_user_message.return_value = MagicMock(id=uuid4())
        mock_session_manager.add_assistant_message.return_value = MagicMock(id=uuid4())
        
        # Mock context builder
        mock_context_builder = MagicMock(spec=ContextBuilder)
        mock_context_builder.build_context.return_value = []
        
        # Create service with mocks
        service = ChatService(
            session_manager=mock_session_manager,
            context_builder=mock_context_builder
        )
        
        # Execute - authenticated user (user_id=123)
        result = service.process_message(
            user_id=123,
            message="What meetings do I have this week?",
            session_id=None,
            event_id=None
        )
        
        # Verify pipeline was called with user_id
        mock_pipeline.process.assert_called_once()
        call_kwargs = mock_pipeline.process.call_args[1]
        assert call_kwargs['user_id'] == 123
        
        # Verify identity_status in metadata
        assert 'identity_status' in result.metadata
        assert result.metadata['identity_status']['source'] == 'authenticated'
        assert result.metadata['identity_status']['disclaimer'] is None

    @patch('indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin')
    @patch('indico_assistant.plugin.AssistantPlugin')
    def test_authenticated_user_non_personal_query_no_prompt(
        self, mock_plugin_class: MagicMock, mock_create_pipeline: MagicMock
    ) -> None:
        """Authenticated user asking non-personal query should proceed normally."""
        from indico_assistant.services.chat.service import ChatService
        from indico_assistant.services.chat.session_manager import SessionManager
        from indico_assistant.services.chat.context_builder import ContextBuilder
        
        # Setup mocks
        mock_plugin = MagicMock()
        mock_plugin_class.instance = mock_plugin
        
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.answer = "There are 50 events this week"
        mock_result.generated_sql = "SELECT COUNT(*) FROM events..."
        mock_result.confidence = 0.90
        mock_result.tables_accessed = []
        mock_result.error = None
        mock_pipeline.process.return_value = mock_result
        mock_create_pipeline.return_value = mock_pipeline
        
        # Mock session manager
        mock_session_manager = MagicMock(spec=SessionManager)
        mock_session = MagicMock()
        mock_session.id = uuid4()
        mock_session.event_id = None
        mock_session.resolved_user_id = None
        mock_session_manager.get_session_or_create.return_value = (mock_session, True)
        mock_session_manager.add_user_message.return_value = MagicMock(id=uuid4())
        mock_session_manager.add_assistant_message.return_value = MagicMock(id=uuid4())
        
        mock_context_builder = MagicMock(spec=ContextBuilder)
        mock_context_builder.build_context.return_value = []
        
        service = ChatService(
            session_manager=mock_session_manager,
            context_builder=mock_context_builder
        )
        
        # Execute - non-personal query
        result = service.process_message(
            user_id=123,
            message="How many events are happening this week?",
            session_id=None,
            event_id=None
        )
        
        # Should proceed to pipeline (not return prompt)
        mock_pipeline.process.assert_called_once()
        assert "identify who you are" not in result.response.lower()


class TestIdentityPromptingFlow:
    """Test unauthenticated user identity prompting flow (T030)."""

    def test_unauthenticated_personal_query_returns_prompt(self) -> None:
        """Unauthenticated user asking personal query should get identity prompt."""
        from indico_assistant.services.chat.service import ChatService
        from indico_assistant.services.chat.session_manager import SessionManager
        from indico_assistant.services.chat.context_builder import ContextBuilder
        from indico_assistant.services.chat.identity import IDENTITY_PROMPT_MESSAGE
        
        # Mock session manager
        mock_session_manager = MagicMock(spec=SessionManager)
        mock_session = MagicMock()
        mock_session.id = uuid4()
        mock_session.event_id = None
        mock_session.resolved_user_id = None
        mock_session_manager.get_session_or_create.return_value = (mock_session, True)
        mock_session_manager.add_user_message.return_value = MagicMock(id=uuid4())
        mock_session_manager.add_assistant_message.return_value = MagicMock(id=uuid4())
        
        mock_context_builder = MagicMock(spec=ContextBuilder)
        mock_context_builder.build_context.return_value = []
        
        service = ChatService(
            session_manager=mock_session_manager,
            context_builder=mock_context_builder
        )
        
        # Execute - unauthenticated user (user_id=None) with personal query
        result = service.process_message(
            user_id=None,
            message="What meetings do I have?",
            session_id=None,
            event_id=None
        )
        
        # Should return identity prompt
        assert result.response == IDENTITY_PROMPT_MESSAGE
        assert result.metadata.get('identity_prompt') is True
        assert result.metadata.get('identity_status', {}).get('source') == 'unknown'

    @patch('indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin')
    @patch('indico_assistant.plugin.AssistantPlugin')
    def test_unauthenticated_non_personal_query_proceeds(
        self, mock_plugin_class: MagicMock, mock_create_pipeline: MagicMock
    ) -> None:
        """Unauthenticated user asking non-personal query should proceed without prompt."""
        from indico_assistant.services.chat.service import ChatService
        from indico_assistant.services.chat.session_manager import SessionManager
        from indico_assistant.services.chat.context_builder import ContextBuilder
        
        # Setup mocks
        mock_plugin = MagicMock()
        mock_plugin_class.instance = mock_plugin
        
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.answer = "There are 25 events"
        mock_result.generated_sql = "SELECT COUNT(*) FROM events"
        mock_result.confidence = 0.85
        mock_result.tables_accessed = []
        mock_result.error = None
        mock_pipeline.process.return_value = mock_result
        mock_create_pipeline.return_value = mock_pipeline
        
        mock_session_manager = MagicMock(spec=SessionManager)
        mock_session = MagicMock()
        mock_session.id = uuid4()
        mock_session.event_id = None
        mock_session.resolved_user_id = None
        mock_session_manager.get_session_or_create.return_value = (mock_session, True)
        mock_session_manager.add_user_message.return_value = MagicMock(id=uuid4())
        mock_session_manager.add_assistant_message.return_value = MagicMock(id=uuid4())
        
        mock_context_builder = MagicMock(spec=ContextBuilder)
        mock_context_builder.build_context.return_value = []
        
        service = ChatService(
            session_manager=mock_session_manager,
            context_builder=mock_context_builder
        )
        
        # Execute - unauthenticated but non-personal query
        result = service.process_message(
            user_id=None,
            message="How many events are there?",
            session_id=None,
            event_id=None
        )
        
        # Should proceed to pipeline (not return prompt)
        mock_pipeline.process.assert_called_once()
        assert "identify who you are" not in result.response.lower()

    @patch('indico_assistant.services.chat.identity.IdentityService.lookup_by_email')
    @patch('indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin')
    @patch('indico_assistant.plugin.AssistantPlugin')
    def test_user_provides_email_identity_resolved(
        self,
        mock_plugin_class: MagicMock,
        mock_create_pipeline: MagicMock,
        mock_lookup_email: MagicMock
    ) -> None:
        """User providing email should have identity resolved."""
        from indico_assistant.services.chat.service import ChatService
        from indico_assistant.services.chat.session_manager import SessionManager
        from indico_assistant.services.chat.context_builder import ContextBuilder
        from indico_assistant.services.chat.identity import IDENTITY_DISCLAIMER
        
        # Mock user lookup
        mock_user = MagicMock()
        mock_user.id = 456
        mock_lookup_email.return_value = mock_user
        
        # Setup pipeline mocks
        mock_plugin = MagicMock()
        mock_plugin_class.instance = mock_plugin
        
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.answer = "You have 2 meetings"
        mock_result.generated_sql = "SELECT * FROM events..."
        mock_result.confidence = 0.90
        mock_result.tables_accessed = []
        mock_result.error = None
        mock_pipeline.process.return_value = mock_result
        mock_create_pipeline.return_value = mock_pipeline
        
        mock_session_manager = MagicMock(spec=SessionManager)
        mock_session = MagicMock()
        mock_session.id = uuid4()
        mock_session.event_id = None
        mock_session.resolved_user_id = None
        mock_session_manager.get_session_or_create.return_value = (mock_session, False)
        mock_session_manager.add_user_message.return_value = MagicMock(id=uuid4())
        mock_session_manager.add_assistant_message.return_value = MagicMock(id=uuid4())
        
        mock_context_builder = MagicMock(spec=ContextBuilder)
        mock_context_builder.build_context.return_value = []
        
        service = ChatService(
            session_manager=mock_session_manager,
            context_builder=mock_context_builder
        )
        
        # Execute - user provides email
        result = service.process_message(
            user_id=None,
            message="My email is john.smith@cern.ch",
            session_id=mock_session.id,
            event_id=None
        )
        
        # Should resolve identity and proceed
        mock_lookup_email.assert_called_once_with('john.smith@cern.ch')
        
        # Identity should be saved to session
        assert mock_session.resolved_user_id == 456
        assert mock_session.identity_source == 'user_provided'
        
        # Response should include disclaimer
        assert IDENTITY_DISCLAIMER in result.response
        assert result.metadata['identity_status']['source'] == 'user_provided'


class TestSessionPersistence:
    """Test session persistence of resolved identity."""

    @patch('indico_assistant.services.chat.service.create_nl2sql_pipeline_from_plugin')
    @patch('indico_assistant.plugin.AssistantPlugin')
    def test_session_identity_reused_on_followup(
        self, mock_plugin_class: MagicMock, mock_create_pipeline: MagicMock
    ) -> None:
        """Previously resolved identity should be reused in follow-up queries."""
        from indico_assistant.services.chat.service import ChatService
        from indico_assistant.services.chat.session_manager import SessionManager
        from indico_assistant.services.chat.context_builder import ContextBuilder
        
        # Setup pipeline mocks
        mock_plugin = MagicMock()
        mock_plugin_class.instance = mock_plugin
        
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.answer = "You have 1 meeting tomorrow"
        mock_result.generated_sql = "SELECT * FROM events..."
        mock_result.confidence = 0.92
        mock_result.tables_accessed = []
        mock_result.error = None
        mock_pipeline.process.return_value = mock_result
        mock_create_pipeline.return_value = mock_pipeline
        
        # Session with previously resolved identity
        mock_session_manager = MagicMock(spec=SessionManager)
        mock_session = MagicMock()
        mock_session.id = uuid4()
        mock_session.event_id = None
        mock_session.resolved_user_id = 789  # Previously resolved
        mock_session.identity_source = 'user_provided'
        mock_session_manager.get_session_or_create.return_value = (mock_session, False)
        mock_session_manager.add_user_message.return_value = MagicMock(id=uuid4())
        mock_session_manager.add_assistant_message.return_value = MagicMock(id=uuid4())
        
        mock_context_builder = MagicMock(spec=ContextBuilder)
        mock_context_builder.build_context.return_value = []
        
        service = ChatService(
            session_manager=mock_session_manager,
            context_builder=mock_context_builder
        )
        
        # Execute - follow-up personal query (no user_id, but session has resolved_user_id)
        result = service.process_message(
            user_id=None,
            message="Do I have any meetings tomorrow?",
            session_id=mock_session.id,
            event_id=None
        )
        
        # Should use session's resolved_user_id
        call_kwargs = mock_pipeline.process.call_args[1]
        assert call_kwargs['user_id'] == 789
        
        # Response should indicate user_provided source
        assert result.metadata['identity_status']['source'] == 'user_provided'
