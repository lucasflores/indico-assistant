# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Unit tests for IdentityService component.

Feature: 016-user-id-passthrough
Task: T028
"""

from unittest.mock import MagicMock, patch

import pytest

from indico_assistant.services.chat.identity import (
    IdentityResolution,
    IdentityService,
    IDENTITY_PROMPT_MESSAGE,
    IDENTITY_DISCLAIMER,
    get_identity_service,
)


@pytest.fixture
def identity_service() -> IdentityService:
    """Create an IdentityService instance."""
    return IdentityService()


class TestIdentityServiceExtraction:
    """Test identity extraction from messages."""

    def test_extract_email(self, identity_service: IdentityService) -> None:
        """Should extract email from message."""
        result = identity_service.extract_identity_from_message(
            "My email is john.smith@cern.ch"
        )
        assert result == ('email', 'john.smith@cern.ch')

    def test_extract_email_with_plus(self, identity_service: IdentityService) -> None:
        """Should extract email with plus addressing."""
        result = identity_service.extract_identity_from_message(
            "You can reach me at test+indico@example.org"
        )
        assert result == ('email', 'test+indico@example.org')

    def test_extract_user_id_with_prefix(self, identity_service: IdentityService) -> None:
        """Should extract user ID with 'user id:' prefix."""
        result = identity_service.extract_identity_from_message(
            "My user id is 12345"
        )
        assert result == ('user_id', '12345')

    def test_extract_user_id_with_equals(self, identity_service: IdentityService) -> None:
        """Should extract user ID with equals sign."""
        result = identity_service.extract_identity_from_message(
            "id=67890"
        )
        assert result == ('user_id', '67890')

    def test_extract_pure_numeric_id(self, identity_service: IdentityService) -> None:
        """Should extract pure numeric input as user ID."""
        result = identity_service.extract_identity_from_message("12345")
        assert result == ('user_id', '12345')

    def test_extract_name_from_my_name_is(self, identity_service: IdentityService) -> None:
        """Should extract name from 'my name is X' pattern."""
        result = identity_service.extract_identity_from_message(
            "My name is John Smith"
        )
        assert result == ('name', 'John Smith')

    def test_extract_name_from_i_am(self, identity_service: IdentityService) -> None:
        """Should extract name from 'I am X' pattern."""
        result = identity_service.extract_identity_from_message(
            "I am Jane Doe"
        )
        assert result == ('name', 'Jane Doe')

    def test_extract_nothing_from_random_text(self, identity_service: IdentityService) -> None:
        """Should return ('none', None) for text without identity info."""
        result = identity_service.extract_identity_from_message(
            "What events are happening this week?"
        )
        assert result == ('none', None)

    def test_email_takes_priority_over_name(self, identity_service: IdentityService) -> None:
        """Email should be extracted first if both present."""
        result = identity_service.extract_identity_from_message(
            "My name is John Smith and my email is john@example.com"
        )
        assert result == ('email', 'john@example.com')


class TestIdentityServiceResolve:
    """Test identity resolution logic."""

    def test_authenticated_user_returns_authenticated_source(
        self, identity_service: IdentityService
    ) -> None:
        """Authenticated user ID should return 'authenticated' source."""
        result = identity_service.resolve_identity(
            user_id=123,
            message="What meetings do I have?",
            session=None
        )
        
        assert result.user_id == 123
        assert result.source == 'authenticated'
        assert result.confidence == 'high'
        assert result.disclaimer is None

    def test_session_resolved_identity_used(
        self, identity_service: IdentityService
    ) -> None:
        """Session's resolved_user_id should be used if present."""
        mock_session = MagicMock()
        mock_session.resolved_user_id = 456
        
        result = identity_service.resolve_identity(
            user_id=None,
            message="Show my events",
            session=mock_session
        )
        
        assert result.user_id == 456
        assert result.source == 'user_provided'
        assert result.disclaimer == IDENTITY_DISCLAIMER

    def test_no_identity_returns_unknown_with_prompt(
        self, identity_service: IdentityService
    ) -> None:
        """Unknown identity should return prompt message."""
        mock_session = MagicMock()
        mock_session.resolved_user_id = None
        
        result = identity_service.resolve_identity(
            user_id=None,
            message="Show my events",
            session=mock_session
        )
        
        assert result.user_id is None
        assert result.source == 'unknown'
        assert result.prompt_message == IDENTITY_PROMPT_MESSAGE

    @patch('indico_assistant.services.chat.identity.IdentityService.lookup_by_email')
    def test_email_in_message_triggers_lookup(
        self, mock_lookup: MagicMock, identity_service: IdentityService
    ) -> None:
        """Email in message should trigger lookup."""
        mock_user = MagicMock()
        mock_user.id = 789
        mock_lookup.return_value = mock_user
        
        mock_session = MagicMock()
        mock_session.resolved_user_id = None
        
        result = identity_service.resolve_identity(
            user_id=None,
            message="My email is test@example.com",
            session=mock_session
        )
        
        mock_lookup.assert_called_once_with('test@example.com')
        assert result.user_id == 789
        assert result.source == 'user_provided'

    @patch('indico_assistant.services.chat.identity.IdentityService.lookup_by_id')
    def test_user_id_in_message_triggers_lookup(
        self, mock_lookup: MagicMock, identity_service: IdentityService
    ) -> None:
        """User ID in message should trigger lookup."""
        mock_user = MagicMock()
        mock_user.id = 12345
        mock_lookup.return_value = mock_user
        
        mock_session = MagicMock()
        mock_session.resolved_user_id = None
        
        result = identity_service.resolve_identity(
            user_id=None,
            message="12345",
            session=mock_session
        )
        
        mock_lookup.assert_called_once_with(12345)
        assert result.user_id == 12345
        assert result.source == 'user_provided'

    @patch('indico_assistant.services.chat.identity.IdentityService.lookup_by_name')
    def test_multiple_name_matches_returns_clarification(
        self, mock_lookup: MagicMock, identity_service: IdentityService
    ) -> None:
        """Multiple name matches should request clarification."""
        mock_user1 = MagicMock()
        mock_user1.id = 1
        mock_user2 = MagicMock()
        mock_user2.id = 2
        mock_user3 = MagicMock()
        mock_user3.id = 3
        mock_lookup.return_value = [mock_user1, mock_user2, mock_user3]
        
        mock_session = MagicMock()
        mock_session.resolved_user_id = None
        
        result = identity_service.resolve_identity(
            user_id=None,
            message="My name is John Smith",
            session=mock_session
        )
        
        assert result.user_id is None
        assert result.source == 'unknown'
        assert result.needs_clarification is True
        assert result.match_count == 3
        assert "3 users" in result.prompt_message


class TestIdentityServiceLookups:
    """Test user lookup methods with mocked database."""

    @patch('indico.modules.users.User')
    def test_lookup_by_email_found(self, mock_user_class: MagicMock) -> None:
        """Should return user when email matches."""
        mock_user = MagicMock()
        mock_user.id = 123
        mock_user_class.query.filter.return_value.first.return_value = mock_user
        
        service = IdentityService()
        result = service.lookup_by_email("test@example.com")
        
        assert result == mock_user

    @patch('indico.modules.users.User')
    def test_lookup_by_email_not_found(self, mock_user_class: MagicMock) -> None:
        """Should return None when email not found."""
        mock_user_class.query.filter.return_value.first.return_value = None
        
        service = IdentityService()
        result = service.lookup_by_email("notfound@example.com")
        
        assert result is None

    @patch('indico.modules.users.User')
    def test_lookup_by_id_found(self, mock_user_class: MagicMock) -> None:
        """Should return user when ID matches."""
        mock_user = MagicMock()
        mock_user.id = 456
        mock_user_class.get.return_value = mock_user
        
        service = IdentityService()
        result = service.lookup_by_id(456)
        
        assert result == mock_user

    @patch('indico.modules.users.User')
    def test_lookup_by_id_not_found(self, mock_user_class: MagicMock) -> None:
        """Should return None when ID not found."""
        mock_user_class.get.return_value = None
        
        service = IdentityService()
        result = service.lookup_by_id(99999)
        
        assert result is None

    def test_lookup_handles_database_error(self) -> None:
        """Should return None on database error (T032)."""
        with patch('indico.modules.users.User') as mock_user_class:
            mock_user_class.query.filter.side_effect = Exception("DB error")
            
            service = IdentityService()
            result = service.lookup_by_email("test@example.com")
            
            assert result is None


class TestIdentityServiceSingleton:
    """Test singleton pattern for identity service."""

    def test_get_identity_service_returns_singleton(self) -> None:
        """get_identity_service should return same instance."""
        service1 = get_identity_service()
        service2 = get_identity_service()
        
        # Same instance
        assert service1 is service2


class TestIdentityResolutionDataclass:
    """Test IdentityResolution dataclass."""

    def test_create_authenticated_resolution(self) -> None:
        """Should create authenticated resolution."""
        resolution = IdentityResolution(
            user_id=123,
            source='authenticated',
            confidence='high'
        )
        
        assert resolution.user_id == 123
        assert resolution.source == 'authenticated'
        assert resolution.confidence == 'high'
        assert resolution.disclaimer is None

    def test_create_user_provided_resolution(self) -> None:
        """Should create user_provided resolution with disclaimer."""
        resolution = IdentityResolution(
            user_id=456,
            source='user_provided',
            confidence='medium',
            disclaimer=IDENTITY_DISCLAIMER
        )
        
        assert resolution.user_id == 456
        assert resolution.source == 'user_provided'
        assert resolution.disclaimer == IDENTITY_DISCLAIMER

    def test_create_unknown_resolution_with_prompt(self) -> None:
        """Should create unknown resolution with prompt."""
        resolution = IdentityResolution(
            user_id=None,
            source='unknown',
            confidence='low',
            prompt_message=IDENTITY_PROMPT_MESSAGE
        )
        
        assert resolution.user_id is None
        assert resolution.source == 'unknown'
        assert resolution.prompt_message == IDENTITY_PROMPT_MESSAGE


class TestIdentityConstants:
    """Test identity-related constants."""

    def test_identity_prompt_message_content(self) -> None:
        """IDENTITY_PROMPT_MESSAGE should contain required elements."""
        assert "name" in IDENTITY_PROMPT_MESSAGE.lower()
        assert "email" in IDENTITY_PROMPT_MESSAGE.lower()
        assert "user id" in IDENTITY_PROMPT_MESSAGE.lower()

    def test_identity_disclaimer_content(self) -> None:
        """IDENTITY_DISCLAIMER should mention verification."""
        assert "log in" in IDENTITY_DISCLAIMER.lower() or "login" in IDENTITY_DISCLAIMER.lower()
