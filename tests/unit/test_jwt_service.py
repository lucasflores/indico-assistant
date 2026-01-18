"""Unit tests for JWT service.

Tests for create_chainlit_token and validate_chainlit_token functions.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import jwt
import pytest

from indico_assistant.services.jwt_service import create_chainlit_token, validate_chainlit_token


class TestCreateChainlitToken:
    """Tests for create_chainlit_token function."""

    def test_creates_valid_jwt_token(self):
        """Token should be a valid JWT string."""
        user = MagicMock()
        user.id = 123
        user.full_name = "John Doe"
        user.email = "john@example.com"

        token = create_chainlit_token(user, "test-secret")

        assert isinstance(token, str)
        assert len(token) > 0
        # Should be a valid JWT (three parts separated by dots)
        assert len(token.split(".")) == 3

    def test_token_contains_user_identifier(self):
        """Token should contain user ID as identifier."""
        user = MagicMock()
        user.id = 456
        user.full_name = "Jane Doe"
        user.email = "jane@example.com"

        token = create_chainlit_token(user, "test-secret")
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])

        assert payload["identifier"] == "456"

    def test_token_contains_user_metadata(self):
        """Token should contain user name and email in metadata."""
        user = MagicMock()
        user.id = 789
        user.full_name = "Test User"
        user.email = "test@example.com"

        token = create_chainlit_token(user, "test-secret")
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])

        assert payload["metadata"]["name"] == "Test User"
        assert payload["metadata"]["email"] == "test@example.com"

    def test_token_uses_email_when_no_full_name(self):
        """Token should use email as name when full_name is None."""
        user = MagicMock()
        user.id = 111
        user.full_name = None
        user.email = "nofullname@example.com"

        token = create_chainlit_token(user, "test-secret")
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])

        assert payload["metadata"]["name"] == "nofullname@example.com"

    def test_token_has_expiration(self):
        """Token should have an expiration claim."""
        user = MagicMock()
        user.id = 222
        user.full_name = "Expiry Test"
        user.email = "expiry@example.com"

        token = create_chainlit_token(user, "test-secret")
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])

        assert "exp" in payload
        # Expiration should be in the future
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp_time > datetime.now(timezone.utc)

    def test_token_expiry_is_configurable(self):
        """Token expiry should respect expiry_hours parameter."""
        user = MagicMock()
        user.id = 333
        user.full_name = "Custom Expiry"
        user.email = "custom@example.com"

        token = create_chainlit_token(user, "test-secret", expiry_hours=1)
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])

        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)

        # Expiry should be within 1-2 hours from now
        diff = exp_time - now
        assert timedelta(minutes=55) < diff < timedelta(hours=2)

    def test_raises_error_for_empty_secret(self):
        """Should raise ValueError when secret is empty."""
        user = MagicMock()
        user.id = 444
        user.full_name = "No Secret"
        user.email = "nosecret@example.com"

        with pytest.raises(ValueError, match="JWT secret cannot be empty"):
            create_chainlit_token(user, "")

    def test_raises_error_for_none_secret(self):
        """Should raise ValueError when secret is None."""
        user = MagicMock()
        user.id = 555
        user.full_name = "None Secret"
        user.email = "nonesecret@example.com"

        with pytest.raises(ValueError, match="JWT secret cannot be empty"):
            create_chainlit_token(user, None)


class TestValidateChainlitToken:
    """Tests for validate_chainlit_token function."""

    def test_validates_valid_token(self):
        """Should return payload for valid token."""
        user = MagicMock()
        user.id = 666
        user.full_name = "Valid Token"
        user.email = "valid@example.com"

        token = create_chainlit_token(user, "test-secret")
        payload = validate_chainlit_token(token, "test-secret")

        assert payload is not None
        assert payload["identifier"] == "666"

    def test_returns_none_for_invalid_signature(self):
        """Should return None for token with wrong secret."""
        user = MagicMock()
        user.id = 777
        user.full_name = "Wrong Secret"
        user.email = "wrong@example.com"

        token = create_chainlit_token(user, "correct-secret")
        payload = validate_chainlit_token(token, "wrong-secret")

        assert payload is None

    def test_returns_none_for_expired_token(self):
        """Should return None for expired token."""
        # Create a manually expired token
        expired_payload = {
            "identifier": "888",
            "metadata": {"name": "Expired", "email": "expired@example.com"},
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = jwt.encode(expired_payload, "test-secret", algorithm="HS256")

        payload = validate_chainlit_token(expired_token, "test-secret")

        assert payload is None

    def test_returns_none_for_malformed_token(self):
        """Should return None for malformed token."""
        payload = validate_chainlit_token("not-a-valid-token", "test-secret")

        assert payload is None

    def test_returns_none_for_empty_token(self):
        """Should return None for empty token."""
        payload = validate_chainlit_token("", "test-secret")

        assert payload is None
