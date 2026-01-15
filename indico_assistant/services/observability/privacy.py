"""PII redaction utilities for privacy-aware tracing.

Feature: 005-langfuse-observability
Tasks: T013, T047, T048, T049

This module provides regex-based PII masking for the "masked" privacy level.
Patterns are applied before content is sent to Langfuse.

Supported patterns:
- Email addresses: user@domain.com → [EMAIL]
- @username mentions: @johndoe → [USERNAME]
"""

from __future__ import annotations

import re
from typing import Optional

from indico_assistant.services.observability import get_observability_logger

logger = get_observability_logger("privacy")


# PII redaction patterns (T047, T048)
# Email pattern: matches standard email formats
EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    re.IGNORECASE
)
EMAIL_REPLACEMENT = "[EMAIL]"

# @username pattern: matches @mentions like @johndoe
USERNAME_PATTERN = re.compile(
    r'@[A-Za-z0-9_]+',
    re.IGNORECASE
)
USERNAME_REPLACEMENT = "[USERNAME]"


def mask_emails(text: str) -> str:
    """Redact email addresses from text (T047).
    
    Args:
        text: Input text potentially containing emails
        
    Returns:
        Text with emails replaced by [EMAIL]
        
    Examples:
        >>> mask_emails("Contact john@example.com for help")
        'Contact [EMAIL] for help'
    """
    return EMAIL_PATTERN.sub(EMAIL_REPLACEMENT, text)


def mask_usernames(text: str) -> str:
    """Redact @username mentions from text (T048).
    
    Args:
        text: Input text potentially containing @mentions
        
    Returns:
        Text with @mentions replaced by [USERNAME]
        
    Examples:
        >>> mask_usernames("Thanks @johndoe for the help")
        'Thanks [USERNAME] for the help'
    """
    return USERNAME_PATTERN.sub(USERNAME_REPLACEMENT, text)


def mask_pii(text: Optional[str]) -> Optional[str]:
    """Apply all PII redaction patterns to text (T049).
    
    Combines all available PII patterns into a single function
    for convenient use in the tracer layer.
    
    Args:
        text: Input text to redact, or None
        
    Returns:
        Redacted text, or None if input was None
        
    Examples:
        >>> mask_pii("Email john@test.com or ping @johndoe")
        'Email [EMAIL] or ping [USERNAME]'
        >>> mask_pii(None)
        None
    """
    if text is None:
        return None
    
    result = text
    result = mask_emails(result)
    result = mask_usernames(result)
    
    return result


def count_pii_occurrences(text: str) -> dict[str, int]:
    """Count PII occurrences in text (for logging/debugging).
    
    Args:
        text: Input text to analyze
        
    Returns:
        Dictionary with counts per PII type
        
    Examples:
        >>> count_pii_occurrences("a@b.com and @user and c@d.org")
        {'emails': 2, 'usernames': 1}
    """
    return {
        "emails": len(EMAIL_PATTERN.findall(text)),
        "usernames": len(USERNAME_PATTERN.findall(text)),
    }


__all__ = [
    "mask_pii",
    "mask_emails",
    "mask_usernames",
    "count_pii_occurrences",
    "EMAIL_PATTERN",
    "USERNAME_PATTERN",
]
