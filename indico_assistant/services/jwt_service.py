"""JWT service for Chainlit authentication.

This module provides JWT token generation for authenticating Indico users
with the Chainlit server. Tokens follow the schema defined in research.md R1:
- identifier: User ID string
- metadata.name: User's full name
- metadata.email: User's email address
- exp: Expiration timestamp (24 hours from creation)
"""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import jwt

if TYPE_CHECKING:
    from indico.modules.users import User


def create_chainlit_token(user: "User", secret: str, expiry_hours: int = 24, event_id: int | None = None) -> str:
    """Create a JWT token for Chainlit authentication.

    Generates a JWT token containing user identity information that can be
    validated by the Chainlit server using the shared secret.

    Args:
        user: The Indico User object to create a token for.
        secret: The shared secret for JWT signing (must match CHAINLIT_AUTH_SECRET).
        expiry_hours: Token validity duration in hours (default: 24).
        event_id: Optional event ID to include in metadata for context-aware queries.

    Returns:
        The encoded JWT token string.

    Raises:
        ValueError: If secret is empty or None.

    Example:
        >>> token = create_chainlit_token(current_user, "my-secret-key", event_id=123)
        >>> # Token can be passed to Chainlit widget via accessToken parameter
    """
    if not secret:
        raise ValueError("JWT secret cannot be empty")

    metadata = {
        "name": user.full_name or user.email,
        "email": user.email,
    }
    if event_id is not None:
        metadata["event_id"] = event_id

    payload = {
        "identifier": str(user.id),
        "metadata": metadata,
        "exp": datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
        "iat": datetime.now(timezone.utc),
    }

    return jwt.encode(payload, secret, algorithm="HS256")


def validate_chainlit_token(token: str, secret: str) -> dict | None:
    """Validate a Chainlit JWT token.

    Decodes and validates a JWT token, checking expiration and signature.

    Args:
        token: The JWT token string to validate.
        secret: The shared secret used for token signing.

    Returns:
        The decoded token payload if valid, None if invalid or expired.

    Example:
        >>> payload = validate_chainlit_token(token, "my-secret-key")
        >>> if payload:
        ...     user_id = payload["identifier"]
    """
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
