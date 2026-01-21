"""Identity resolution service for user identification.

Feature: 016-user-id-passthrough
Task: T003, T013-T018, T022-T023

Provides user lookup and identity resolution for the chat service when
authentication context is not available (e.g., Chainlit widget users).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from indico_assistant.models.session import ChatSession
    from indico.modules.users import User

logger = logging.getLogger(__name__)


# T018: Identity prompting message constant
IDENTITY_PROMPT_MESSAGE = (
    "I can't seem to identify who you are right now. To help with your personal query, "
    "could you please provide one of the following:\n"
    "- Your full name (e.g., \"John Smith\")\n"
    "- Your email address\n"
    "- Your Indico user ID (preferred for accuracy)\n\n"
    "Once you provide this information, I'll be able to answer your question!"
)

# T023: Disclaimer for user-provided identity
IDENTITY_DISCLAIMER = (
    "Note: These results are based on the identity you provided. "
    "For verified access, please log in."
)


@dataclass
class IdentityResolution:
    """Result of identity resolution attempt.
    
    Attributes:
        user_id: Resolved user ID (or None if unknown)
        source: How identity was determined ('authenticated', 'user_provided', 'unknown')
        confidence: Confidence level ('high', 'medium', 'low')
        disclaimer: Disclaimer text if user_provided
        needs_clarification: True if multiple matches found
        match_count: Number of users matched (for disambiguation)
        prompt_message: Message to prompt user for identity (if needed)
    """
    user_id: int | None
    source: str  # 'authenticated', 'user_provided', 'unknown'
    confidence: str  # 'high' (authenticated), 'medium' (exact match), 'low' (partial)
    disclaimer: str | None = None
    needs_clarification: bool = False
    match_count: int = 0
    prompt_message: str | None = None


class IdentityService:
    """Service for resolving user identity from various sources.
    
    Handles user lookup by email, name, or ID when authentication
    context is not available.
    """

    # Patterns for extracting identity info from messages
    EMAIL_PATTERN = re.compile(r'\b[\w.+-]+@[\w.-]+\.\w+\b', re.IGNORECASE)
    USER_ID_PATTERN = re.compile(r'\b(?:user\s*id\s*(?:is\s*)?[:=]?\s*|id\s*(?:is\s*)?[:=]?\s*)(\d+)\b', re.IGNORECASE)
    # Pattern for direct numeric input (e.g., "12345" as response to "provide your user ID")
    NUMERIC_ID_PATTERN = re.compile(r'^\s*(\d+)\s*$')

    def lookup_by_email(self, email: str) -> "User | None":
        """Look up a user by email address.
        
        Args:
            email: Email address to search for
            
        Returns:
            User if found, None otherwise
            
        Task: T013
        """
        try:
            from indico.modules.users import User
            
            # Use all_emails to match primary and secondary emails
            user = User.query.filter(
                User.all_emails.contains(email.lower())
            ).first()
            
            if user:
                logger.debug(f"Found user by email: user_id={user.id}")
            else:
                logger.debug(f"No user found for email: {email}")
            
            return user
        except Exception:
            logger.exception("Error looking up user by email")
            return None

    def lookup_by_name(self, first_name: str, last_name: str) -> list:
        """Look up users by name (case-insensitive).
        
        Args:
            first_name: First name to search for
            last_name: Last name to search for
            
        Returns:
            List of matching User objects
            
        Task: T014
        """
        try:
            from indico.modules.users import User
            from indico.core.db import db
            
            users = User.query.filter(
                db.func.lower(User.first_name) == first_name.lower(),
                db.func.lower(User.last_name) == last_name.lower()
            ).all()
            
            logger.debug(f"Found {len(users)} users matching name: {first_name} {last_name}")
            return users
        except Exception:
            logger.exception("Error looking up user by name")
            return []

    def lookup_by_id(self, user_id: int) -> "User | None":
        """Look up a user by their Indico user ID.
        
        Args:
            user_id: Indico user ID
            
        Returns:
            User if found, None otherwise
            
        Task: T015
        """
        try:
            from indico.modules.users import User
            
            user = User.get(user_id)
            if user:
                logger.debug(f"Found user by ID: user_id={user.id}")
            else:
                logger.debug(f"No user found for ID: {user_id}")
            return user
        except Exception:
            logger.exception("Error looking up user by ID")
            return None

    def extract_identity_from_message(self, message: str) -> tuple[str, str | None]:
        """Extract identity information from a user message.
        
        Detects email addresses, user IDs, and names in the message.
        
        Args:
            message: User message that may contain identity info
            
        Returns:
            Tuple of (identity_type, identity_value):
            - ('email', 'user@example.com')
            - ('user_id', '12345')
            - ('name', 'John Smith')
            - ('none', None)
            
        Task: T016
        """
        # Check for email first (most reliable)
        email_match = self.EMAIL_PATTERN.search(message)
        if email_match:
            return ('email', email_match.group(0))
        
        # Check for explicit user ID
        id_match = self.USER_ID_PATTERN.search(message)
        if id_match:
            return ('user_id', id_match.group(1))
        
        # Check for pure numeric input (user responding with just their ID)
        numeric_match = self.NUMERIC_ID_PATTERN.match(message)
        if numeric_match:
            return ('user_id', numeric_match.group(1))
        
        # Try to extract name (look for "my name is X" or "I am X" patterns)
        name_patterns = [
            r"(?:my\s+name\s+is|i'?m|i\s+am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)$",  # Just a name on its own line
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return ('name', match.group(1))
        
        return ('none', None)

    def resolve_identity(
        self,
        user_id: int | None,
        message: str,
        session: Optional["ChatSession"] = None
    ) -> IdentityResolution:
        """Resolve user identity from available sources.
        
        Resolution order:
        1. Use authenticated user_id if available
        2. Use session's resolved_user_id if available
        3. Try to extract and lookup from message
        4. Return unknown status (prompting may be needed)
        
        Args:
            user_id: Authenticated user ID (or None)
            message: Current user message
            session: Current chat session (may have resolved identity)
            
        Returns:
            IdentityResolution with resolved user info
            
        Task: T017
        """
        # 1. Authenticated user has highest priority
        if user_id is not None:
            return IdentityResolution(
                user_id=user_id,
                source='authenticated',
                confidence='high'
            )
        
        # 2. Check session for previously resolved identity
        if session is not None and session.resolved_user_id is not None:
            return IdentityResolution(
                user_id=session.resolved_user_id,
                source='user_provided',
                confidence='medium',
                disclaimer=IDENTITY_DISCLAIMER
            )
        
        # 3. Try to extract identity from message
        identity_type, identity_value = self.extract_identity_from_message(message)
        
        if identity_type == 'email' and identity_value:
            user = self.lookup_by_email(identity_value)
            if user:
                return IdentityResolution(
                    user_id=user.id,
                    source='user_provided',
                    confidence='medium',
                    disclaimer=IDENTITY_DISCLAIMER
                )
        
        if identity_type == 'user_id' and identity_value:
            user = self.lookup_by_id(int(identity_value))
            if user:
                return IdentityResolution(
                    user_id=user.id,
                    source='user_provided',
                    confidence='medium',
                    disclaimer=IDENTITY_DISCLAIMER
                )
        
        if identity_type == 'name' and identity_value:
            # Parse name into first/last
            parts = identity_value.strip().split()
            if len(parts) >= 2:
                first_name = parts[0]
                last_name = ' '.join(parts[1:])
                users = self.lookup_by_name(first_name, last_name)
                
                # T022: Handle multiple matches
                if len(users) == 1:
                    return IdentityResolution(
                        user_id=users[0].id,
                        source='user_provided',
                        confidence='medium',
                        disclaimer=IDENTITY_DISCLAIMER
                    )
                elif len(users) > 1:
                    return IdentityResolution(
                        user_id=None,
                        source='unknown',
                        confidence='low',
                        needs_clarification=True,
                        match_count=len(users),
                        prompt_message=(
                            f"I found {len(users)} users with the name {identity_value}. "
                            "Could you please provide your email address or user ID "
                            "so I can identify you correctly?"
                        )
                    )
        
        # 4. Identity unknown
        return IdentityResolution(
            user_id=None,
            source='unknown',
            confidence='low',
            prompt_message=IDENTITY_PROMPT_MESSAGE
        )


# Default instance
_identity_service: IdentityService | None = None


def get_identity_service() -> IdentityService:
    """Get or create the default identity service instance.
    
    Returns:
        IdentityService instance
    """
    global _identity_service
    if _identity_service is None:
        _identity_service = IdentityService()
    return _identity_service
