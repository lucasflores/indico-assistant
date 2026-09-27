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

    @pytest.mark.parametrize(("kwargs", "stored"), [
        ({"feedback_type": "thumbs_up"}, True),
        ({"feedback_type": "rating", "rating": 4}, 4),
        ({"feedback_type": "comment", "comment": "Very helpful!"}, "Very helpful!"),
    ])
    def test_submit_feedback_stores_one_value_per_type(self, feedback_service, kwargs, stored):
        """The model keeps (message, user, type) -> value; the service used a create() that never existed."""
        message_id = uuid4()
        with patch('indico_assistant.services.feedback.service.ChatMessage') as mock_msg_cls, \
                patch('indico_assistant.services.feedback.service.FeedbackEntry') as mock_fb_cls:
            mock_msg_cls.query.with_for_update.return_value.filter_by.return_value.first.return_value = MagicMock(id=message_id, session=MagicMock(user_id=123))
            result = feedback_service.submit_feedback(user_id=123, message_id=message_id, **kwargs)
        mock_fb_cls.create_or_update.assert_called_once_with(
            message_id=message_id, user_id=123, feedback_type=kwargs["feedback_type"], value=stored)
        assert result is mock_fb_cls.create_or_update.return_value

    def test_switching_thumbs_replaces_the_other_vote(self, feedback_service):
        message_id = uuid4()
        with patch('indico_assistant.services.feedback.service.ChatMessage') as mock_msg_cls, \
                patch('indico_assistant.services.feedback.service.FeedbackEntry') as mock_fb_cls:
            mock_msg_cls.query.with_for_update.return_value.filter_by.return_value.first.return_value = MagicMock(id=message_id, session=MagicMock(user_id=123))
            feedback_service.submit_feedback(user_id=123, message_id=message_id, feedback_type="thumbs_down")
        mock_fb_cls.query.filter.return_value.delete.assert_called_once_with(synchronize_session=False)
        mock_msg_cls.query.with_for_update.assert_called_once_with()  # concurrent votes are serialised

    def test_submit_feedback_message_not_found(self, feedback_service):
        """Test error when message doesn't exist."""
        message_id = uuid4()
        
        with patch('indico_assistant.services.feedback.service.ChatMessage') as mock_msg_cls:
            mock_msg_cls.query.with_for_update.return_value.filter_by.return_value.first.return_value = None
            
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
            mock_msg_cls.query.with_for_update.return_value.filter_by.return_value.first.return_value = mock_message
            
            with pytest.raises(MessageAccessDeniedError):
                feedback_service.submit_feedback(
                    user_id=123,  # Different from session owner
                    message_id=message_id,
                    feedback_type="thumbs_up"
                )


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
