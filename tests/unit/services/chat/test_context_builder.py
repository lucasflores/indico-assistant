"""Unit tests for ContextBuilder service.

Feature: 004-chat-api
Task: T019
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from indico_assistant.services.chat.context_builder import (
    ContextBuilder,
    get_context_builder,
)


class TestContextBuilder:
    """Tests for ContextBuilder class."""

    def test_init_default_max_pairs(self):
        """Test initialization with default max_pairs."""
        with patch('indico_assistant.services.chat.context_builder.ChatMessage'):
            builder = ContextBuilder()
            assert builder._max_pairs == 10

    def test_init_custom_max_pairs(self):
        """Test initialization with custom max_pairs."""
        with patch('indico_assistant.services.chat.context_builder.ChatMessage'):
            builder = ContextBuilder(max_pairs=5)
            assert builder._max_pairs == 5

    def test_build_context_empty_session(self):
        """Test building context for session with no messages."""
        session_id = uuid4()
        
        with patch('indico_assistant.services.chat.context_builder.ChatMessage') as mock_cls:
            mock_query = MagicMock()
            mock_cls.query.filter_by.return_value = mock_query
            mock_query.order_by.return_value.limit.return_value.all.return_value = []
            
            builder = ContextBuilder()
            result = builder.build_context(session_id)
            
            assert result == []

    def test_build_context_with_messages(self):
        """Test building context with message pairs."""
        session_id = uuid4()
        
        # Create mock messages in reverse order (DB returns desc)
        mock_messages = []
        for i, (role, content) in enumerate([
            ("assistant", "The first event is 'Team Meeting' at 9 AM."),
            ("user", "Show details for the first one"),
            ("assistant", "There are 3 events tomorrow."),
            ("user", "What events are tomorrow?"),
        ]):
            msg = MagicMock()
            msg.role = role
            msg.content = content
            mock_messages.append(msg)
        
        with patch('indico_assistant.services.chat.context_builder.ChatMessage') as mock_cls:
            mock_query = MagicMock()
            mock_cls.query.filter_by.return_value = mock_query
            mock_query.order_by.return_value.limit.return_value.all.return_value = mock_messages
            
            builder = ContextBuilder()
            result = builder.build_context(session_id)
            
            # Should be reversed to chronological order
            assert len(result) == 4
            assert result[0] == {"role": "user", "content": "What events are tomorrow?"}
            assert result[1] == {"role": "assistant", "content": "There are 3 events tomorrow."}
            assert result[2] == {"role": "user", "content": "Show details for the first one"}
            assert result[3] == {"role": "assistant", "content": "The first event is 'Team Meeting' at 9 AM."}

    def test_build_context_respects_max_pairs(self):
        """Test that context building respects max_pairs limit."""
        session_id = uuid4()
        
        with patch('indico_assistant.services.chat.context_builder.ChatMessage') as mock_cls:
            mock_query = MagicMock()
            mock_cls.query.filter_by.return_value = mock_query
            mock_query.order_by.return_value.limit.return_value.all.return_value = []
            
            builder = ContextBuilder(max_pairs=2)
            builder.build_context(session_id)
            
            # Should limit to max_pairs * 2 messages
            mock_query.order_by.return_value.limit.assert_called_once_with(4)

    def test_build_context_with_metadata(self):
        """Test building context with metadata included."""
        session_id = uuid4()
        
        mock_msg = MagicMock()
        mock_msg.role = "assistant"
        mock_msg.content = "There are 5 events."
        mock_msg.metadata_json = {"sql_generated": "SELECT COUNT(*) FROM events"}
        
        with patch('indico_assistant.services.chat.context_builder.ChatMessage') as mock_cls:
            mock_query = MagicMock()
            mock_cls.query.filter_by.return_value = mock_query
            mock_query.order_by.return_value.limit.return_value.all.return_value = [mock_msg]
            
            builder = ContextBuilder()
            result = builder.build_context_with_metadata(session_id)
            
            assert len(result) == 1
            assert result[0]["metadata"] == {"sql_generated": "SELECT COUNT(*) FROM events"}


class TestGetContextBuilder:
    """Tests for get_context_builder factory function."""

    def test_get_context_builder_returns_instance(self):
        """Test factory function returns a ContextBuilder."""
        with patch('indico_assistant.services.chat.context_builder.ChatMessage'):
            import indico_assistant.services.chat.context_builder as module
            module._context_builder = None
            
            builder = get_context_builder()
            
            assert isinstance(builder, ContextBuilder)

    def test_get_context_builder_returns_same_instance(self):
        """Test factory function returns same instance (singleton)."""
        with patch('indico_assistant.services.chat.context_builder.ChatMessage'):
            import indico_assistant.services.chat.context_builder as module
            module._context_builder = None
            
            builder1 = get_context_builder()
            builder2 = get_context_builder()
            
            assert builder1 is builder2
