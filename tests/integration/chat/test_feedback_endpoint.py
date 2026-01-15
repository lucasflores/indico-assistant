"""Integration tests for POST /feedback endpoint.

Feature: 004-chat-api
Task: T036
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestFeedbackEndpointIntegration:
    """Integration tests for the feedback endpoint."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock authenticated user."""
        user = MagicMock()
        user.id = 123
        user.is_admin = False
        return user

    @pytest.fixture
    def feedback_controller(self, mock_user):
        """Create a feedback controller instance."""
        from indico_assistant.controllers.feedback import RHFeedback
        
        ctrl = RHFeedback.__new__(RHFeedback)
        ctrl.user = mock_user
        return ctrl

    def test_submit_thumbs_up_feedback(self, feedback_controller):
        """Test submitting thumbs up feedback."""
        message_id = uuid4()
        feedback_id = uuid4()
        
        with patch('indico_assistant.controllers.feedback.request') as mock_request:
            mock_request.get_json.return_value = {
                "message_id": str(message_id),
                "feedback_type": "thumbs_up"
            }
            
            with patch('indico_assistant.controllers.feedback.get_feedback_service') as mock_get:
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                
                mock_feedback = MagicMock()
                mock_feedback.id = feedback_id
                mock_feedback.message_id = message_id
                mock_feedback.feedback_type = "thumbs_up"
                mock_feedback.created_at = datetime.now(timezone.utc)
                mock_service.submit_feedback.return_value = mock_feedback
                
                with patch('indico_assistant.controllers.feedback.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status = feedback_controller._process()
                    
                    assert status == 201
                    data = response.get_json()
                    assert data["feedback_id"] == str(feedback_id)
                    assert data["feedback_type"] == "thumbs_up"
                    mock_service.commit.assert_called_once()

    def test_submit_thumbs_down_feedback(self, feedback_controller):
        """Test submitting thumbs down feedback."""
        message_id = uuid4()
        feedback_id = uuid4()
        
        with patch('indico_assistant.controllers.feedback.request') as mock_request:
            mock_request.get_json.return_value = {
                "message_id": str(message_id),
                "feedback_type": "thumbs_down"
            }
            
            with patch('indico_assistant.controllers.feedback.get_feedback_service') as mock_get:
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                
                mock_feedback = MagicMock()
                mock_feedback.id = feedback_id
                mock_feedback.message_id = message_id
                mock_feedback.feedback_type = "thumbs_down"
                mock_feedback.created_at = datetime.now(timezone.utc)
                mock_service.submit_feedback.return_value = mock_feedback
                
                with patch('indico_assistant.controllers.feedback.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status = feedback_controller._process()
                    
                    assert status == 201
                    data = response.get_json()
                    assert data["feedback_type"] == "thumbs_down"

    def test_submit_rating_feedback(self, feedback_controller):
        """Test submitting numeric rating feedback."""
        message_id = uuid4()
        feedback_id = uuid4()
        
        with patch('indico_assistant.controllers.feedback.request') as mock_request:
            mock_request.get_json.return_value = {
                "message_id": str(message_id),
                "feedback_type": "rating",
                "rating": 4
            }
            
            with patch('indico_assistant.controllers.feedback.get_feedback_service') as mock_get:
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                
                mock_feedback = MagicMock()
                mock_feedback.id = feedback_id
                mock_feedback.message_id = message_id
                mock_feedback.feedback_type = "rating"
                mock_feedback.created_at = datetime.now(timezone.utc)
                mock_service.submit_feedback.return_value = mock_feedback
                
                with patch('indico_assistant.controllers.feedback.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status = feedback_controller._process()
                    
                    assert status == 201
                    mock_service.submit_feedback.assert_called_once()
                    call_kwargs = mock_service.submit_feedback.call_args[1]
                    assert call_kwargs['rating'] == 4

    def test_submit_comment_feedback(self, feedback_controller):
        """Test submitting comment feedback."""
        message_id = uuid4()
        feedback_id = uuid4()
        
        with patch('indico_assistant.controllers.feedback.request') as mock_request:
            mock_request.get_json.return_value = {
                "message_id": str(message_id),
                "feedback_type": "comment",
                "comment": "This was very helpful!"
            }
            
            with patch('indico_assistant.controllers.feedback.get_feedback_service') as mock_get:
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                
                mock_feedback = MagicMock()
                mock_feedback.id = feedback_id
                mock_feedback.message_id = message_id
                mock_feedback.feedback_type = "comment"
                mock_feedback.created_at = datetime.now(timezone.utc)
                mock_service.submit_feedback.return_value = mock_feedback
                
                with patch('indico_assistant.controllers.feedback.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status = feedback_controller._process()
                    
                    assert status == 201
                    call_kwargs = mock_service.submit_feedback.call_args[1]
                    assert call_kwargs['comment'] == "This was very helpful!"

    def test_feedback_updates_existing(self, feedback_controller):
        """Test that feedback updates existing entry."""
        message_id = uuid4()
        feedback_id = uuid4()
        
        with patch('indico_assistant.controllers.feedback.request') as mock_request:
            mock_request.get_json.return_value = {
                "message_id": str(message_id),
                "feedback_type": "thumbs_up"  # Changed from previous thumbs_down
            }
            
            with patch('indico_assistant.controllers.feedback.get_feedback_service') as mock_get:
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                
                # Return existing feedback that was updated
                mock_feedback = MagicMock()
                mock_feedback.id = feedback_id
                mock_feedback.message_id = message_id
                mock_feedback.feedback_type = "thumbs_up"
                mock_feedback.created_at = datetime.now(timezone.utc)
                mock_service.submit_feedback.return_value = mock_feedback
                
                with patch('indico_assistant.controllers.feedback.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status = feedback_controller._process()
                    
                    # Still returns 201 even for updates
                    assert status == 201

    def test_feedback_message_not_found(self, feedback_controller):
        """Test 404 when message doesn't exist."""
        message_id = uuid4()
        
        with patch('indico_assistant.controllers.feedback.request') as mock_request:
            mock_request.get_json.return_value = {
                "message_id": str(message_id),
                "feedback_type": "thumbs_up"
            }
            
            with patch('indico_assistant.controllers.feedback.get_feedback_service') as mock_get:
                from indico_assistant.services.feedback import MessageNotFoundError
                
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                mock_service.submit_feedback.side_effect = MessageNotFoundError(
                    f"Message {message_id} not found"
                )
                
                with patch('indico_assistant.controllers.feedback.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status = feedback_controller._process()
                    
                    assert status == 404
                    data = response.get_json()
                    assert data["code"] == "MESSAGE_NOT_FOUND"

    def test_feedback_access_denied(self, feedback_controller):
        """Test 403 when user doesn't own the session."""
        message_id = uuid4()
        
        with patch('indico_assistant.controllers.feedback.request') as mock_request:
            mock_request.get_json.return_value = {
                "message_id": str(message_id),
                "feedback_type": "thumbs_up"
            }
            
            with patch('indico_assistant.controllers.feedback.get_feedback_service') as mock_get:
                from indico_assistant.services.feedback import MessageAccessDeniedError
                
                mock_service = MagicMock()
                mock_get.return_value = mock_service
                mock_service.submit_feedback.side_effect = MessageAccessDeniedError(
                    "Cannot provide feedback on others' messages"
                )
                
                with patch('indico_assistant.controllers.feedback.get_rate_limiter') as mock_limiter:
                    from indico_assistant.services.chat.rate_limiter import RateLimitResult
                    mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                        allowed=True, remaining=59, retry_after=None
                    )
                    
                    response, status = feedback_controller._process()
                    
                    assert status == 403
                    data = response.get_json()
                    assert data["code"] == "ACCESS_DENIED"

    def test_feedback_validation_error_missing_message_id(self, feedback_controller):
        """Test validation error when message_id missing."""
        with patch('indico_assistant.controllers.feedback.request') as mock_request:
            mock_request.get_json.return_value = {
                "feedback_type": "thumbs_up"
            }
            
            with patch('indico_assistant.controllers.feedback.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=59, retry_after=None
                )
                
                response, status = feedback_controller._process()
                
                assert status == 422

    def test_feedback_validation_error_missing_feedback_type(self, feedback_controller):
        """Test validation error when feedback_type missing."""
        message_id = uuid4()
        
        with patch('indico_assistant.controllers.feedback.request') as mock_request:
            mock_request.get_json.return_value = {
                "message_id": str(message_id)
            }
            
            with patch('indico_assistant.controllers.feedback.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=59, retry_after=None
                )
                
                response, status = feedback_controller._process()
                
                assert status == 422

    def test_feedback_validation_error_invalid_uuid(self, feedback_controller):
        """Test validation error for invalid message_id format."""
        with patch('indico_assistant.controllers.feedback.request') as mock_request:
            mock_request.get_json.return_value = {
                "message_id": "not-a-uuid",
                "feedback_type": "thumbs_up"
            }
            
            with patch('indico_assistant.controllers.feedback.get_rate_limiter') as mock_limiter:
                from indico_assistant.services.chat.rate_limiter import RateLimitResult
                mock_limiter.return_value.check_rate.return_value = RateLimitResult(
                    allowed=True, remaining=59, retry_after=None
                )
                
                response, status = feedback_controller._process()
                
                assert status == 422
