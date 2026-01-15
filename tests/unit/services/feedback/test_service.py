"""Unit tests for FeedbackService.

Feature: 004-chat-api
Task: T035
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from indico_assistant.services.feedback.service import (
    FeedbackService,
    FeedbackServiceError,
    MessageAccessDeniedError,
    MessageNotFoundError,
    get_feedback_service,
)


class TestFeedbackService:
    """Tests for FeedbackService class."""

    @pytest.fixture
    def feedback_service(self):
        """Create a FeedbackService instance with mocked db."""
        with patch('indico_assistant.services.feedback.service.db') as mock_db:
            mock_db.session = MagicMock()
            service = FeedbackService()
            yield service

    def test_submit_feedback_creates_new_entry(self, feedback_service):
        """Test creating new feedback entry."""
        message_id = uuid4()
        
        mock_message = MagicMock()
        mock_message.id = message_id
        mock_message.session.user_id = 123
        
        mock_feedback = MagicMock()
        mock_feedback.id = uuid4()
        mock_feedback.message_id = message_id
        mock_feedback.feedback_type = "thumbs_up"
        
        with patch('indico_assistant.services.feedback.service.ChatMessage') as mock_msg_cls:
            mock_msg_cls.query.get.return_value = mock_message
            
            with patch('indico_assistant.services.feedback.service.FeedbackEntry') as mock_fb_cls:
                mock_fb_cls.query.filter_by.return_value.first.return_value = None
                mock_fb_cls.create.return_value = mock_feedback
                
                result = feedback_service.submit_feedback(
                    user_id=123,
                    message_id=message_id,
                    feedback_type="thumbs_up"
                )
                
                mock_fb_cls.create.assert_called_once()
                assert result == mock_feedback

    def test_submit_feedback_updates_existing_entry(self, feedback_service):
        """Test updating existing feedback entry."""
        message_id = uuid4()
        
        mock_message = MagicMock()
        mock_message.id = message_id
        mock_message.session.user_id = 123
        
        existing_feedback = MagicMock()
        existing_feedback.id = uuid4()
        existing_feedback.feedback_type = "thumbs_down"
        
        with patch('indico_assistant.services.feedback.service.ChatMessage') as mock_msg_cls:
            mock_msg_cls.query.get.return_value = mock_message
            
            with patch('indico_assistant.services.feedback.service.FeedbackEntry') as mock_fb_cls:
                mock_fb_cls.query.filter_by.return_value.first.return_value = existing_feedback
                
                result = feedback_service.submit_feedback(
                    user_id=123,
                    message_id=message_id,
                    feedback_type="thumbs_up"  # Changed from thumbs_down
                )
                
                assert existing_feedback.feedback_type == "thumbs_up"
                assert result == existing_feedback
                mock_fb_cls.create.assert_not_called()

    def test_submit_feedback_message_not_found(self, feedback_service):
        """Test error when message doesn't exist."""
        message_id = uuid4()
        
        with patch('indico_assistant.services.feedback.service.ChatMessage') as mock_msg_cls:
            mock_msg_cls.query.get.return_value = None
            
            with pytest.raises(MessageNotFoundError):
                feedback_service.submit_feedback(
                    user_id=123,
                    message_id=message_id,
                    feedback_type="thumbs_up"
                )

    def test_submit_feedback_access_denied(self, feedback_service):
        """Test error when user doesn't own the session."""
        message_id = uuid4()
        
        mock_message = MagicMock()
        mock_message.id = message_id
        mock_message.session.user_id = 456  # Different user
        
        with patch('indico_assistant.services.feedback.service.ChatMessage') as mock_msg_cls:
            mock_msg_cls.query.get.return_value = mock_message
            
            with pytest.raises(MessageAccessDeniedError):
                feedback_service.submit_feedback(
                    user_id=123,  # Different from session owner
                    message_id=message_id,
                    feedback_type="thumbs_up"
                )

    def test_submit_feedback_with_rating(self, feedback_service):
        """Test creating feedback with numeric rating."""
        message_id = uuid4()
        
        mock_message = MagicMock()
        mock_message.id = message_id
        mock_message.session.user_id = 123
        
        mock_feedback = MagicMock()
        mock_feedback.id = uuid4()
        mock_feedback.rating = 4
        
        with patch('indico_assistant.services.feedback.service.ChatMessage') as mock_msg_cls:
            mock_msg_cls.query.get.return_value = mock_message
            
            with patch('indico_assistant.services.feedback.service.FeedbackEntry') as mock_fb_cls:
                mock_fb_cls.query.filter_by.return_value.first.return_value = None
                mock_fb_cls.create.return_value = mock_feedback
                
                result = feedback_service.submit_feedback(
                    user_id=123,
                    message_id=message_id,
                    feedback_type="rating",
                    rating=4
                )
                
                call_kwargs = mock_fb_cls.create.call_args[1]
                assert call_kwargs['rating'] == 4

    def test_submit_feedback_with_comment(self, feedback_service):
        """Test creating feedback with comment."""
        message_id = uuid4()
        
        mock_message = MagicMock()
        mock_message.id = message_id
        mock_message.session.user_id = 123
        
        mock_feedback = MagicMock()
        mock_feedback.id = uuid4()
        mock_feedback.comment = "Very helpful!"
        
        with patch('indico_assistant.services.feedback.service.ChatMessage') as mock_msg_cls:
            mock_msg_cls.query.get.return_value = mock_message
            
            with patch('indico_assistant.services.feedback.service.FeedbackEntry') as mock_fb_cls:
                mock_fb_cls.query.filter_by.return_value.first.return_value = None
                mock_fb_cls.create.return_value = mock_feedback
                
                result = feedback_service.submit_feedback(
                    user_id=123,
                    message_id=message_id,
                    feedback_type="comment",
                    comment="Very helpful!"
                )
                
                call_kwargs = mock_fb_cls.create.call_args[1]
                assert call_kwargs['comment'] == "Very helpful!"


class TestValidateMessageAccess:
    """Tests for _validate_message_access method."""

    @pytest.fixture
    def feedback_service(self):
        """Create a FeedbackService instance."""
        with patch('indico_assistant.services.feedback.service.db'):
            return FeedbackService()

    def test_access_granted_same_user(self, feedback_service):
        """Test access granted when user owns session."""
        mock_message = MagicMock()
        mock_message.session.user_id = 123
        
        result = feedback_service._validate_message_access(mock_message, 123)
        
        assert result is True

    def test_access_denied_different_user(self, feedback_service):
        """Test access denied when different user."""
        mock_message = MagicMock()
        mock_message.session.user_id = 456
        
        result = feedback_service._validate_message_access(mock_message, 123)
        
        assert result is False


class TestGetFeedbackForMessage:
    """Tests for get_feedback_for_message method."""

    @pytest.fixture
    def feedback_service(self):
        """Create a FeedbackService instance."""
        with patch('indico_assistant.services.feedback.service.db'):
            return FeedbackService()

    def test_returns_feedback_entries(self, feedback_service):
        """Test retrieving feedback for a message."""
        message_id = uuid4()
        mock_feedback = [MagicMock(), MagicMock()]
        
        with patch('indico_assistant.services.feedback.service.FeedbackEntry') as mock_cls:
            mock_cls.query.filter_by.return_value.all.return_value = mock_feedback
            
            result = feedback_service.get_feedback_for_message(message_id)
            
            mock_cls.query.filter_by.assert_called_once_with(message_id=message_id)
            assert result == mock_feedback


class TestGetUserFeedback:
    """Tests for get_user_feedback method."""

    @pytest.fixture
    def feedback_service(self):
        """Create a FeedbackService instance."""
        with patch('indico_assistant.services.feedback.service.db'):
            return FeedbackService()

    def test_returns_user_feedback_with_pagination(self, feedback_service):
        """Test retrieving user's feedback with pagination."""
        mock_feedback = [MagicMock() for _ in range(5)]
        
        with patch('indico_assistant.services.feedback.service.FeedbackEntry') as mock_cls:
            mock_query = MagicMock()
            mock_cls.query.filter_by.return_value = mock_query
            mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = mock_feedback
            
            result = feedback_service.get_user_feedback(
                user_id=123,
                limit=10,
                offset=5
            )
            
            assert result == mock_feedback


class TestGetFeedbackService:
    """Tests for get_feedback_service factory function."""

    def test_returns_instance(self):
        """Test factory returns FeedbackService."""
        with patch('indico_assistant.services.feedback.service.db'):
            import indico_assistant.services.feedback.service as module
            module._feedback_service = None
            
            service = get_feedback_service()
            
            assert isinstance(service, FeedbackService)

    def test_returns_same_instance(self):
        """Test factory returns singleton."""
        with patch('indico_assistant.services.feedback.service.db'):
            import indico_assistant.services.feedback.service as module
            module._feedback_service = None
            
            service1 = get_feedback_service()
            service2 = get_feedback_service()
            
            assert service1 is service2
