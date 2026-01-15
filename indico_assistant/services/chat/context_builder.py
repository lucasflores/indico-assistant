"""Context builder service for chat conversation history.

Builds conversation context from previous messages in a session
to provide the LLM with relevant history for follow-up questions.

Feature: 004-chat-api
Task: T013
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from indico_assistant.models.message import ChatMessage


class ContextBuilder:
    """Builds conversation context for LLM prompts.
    
    Retrieves recent messages from a session and formats them
    as a list of role/content pairs suitable for LLM context.
    
    Default behavior:
    - Returns up to 10 message pairs (20 messages total)
    - Orders messages chronologically (oldest first)
    - Includes role and content for each message
    
    Attributes:
        MAX_PAIRS: Maximum number of message pairs to include
    """
    
    MAX_PAIRS = 10  # Per FR-007: Last 10 message pairs

    def __init__(self, max_pairs: int | None = None):
        """Initialize the context builder.
        
        Args:
            max_pairs: Override default max pairs (optional)
        """
        self._max_pairs = max_pairs or self.MAX_PAIRS

    def build_context(self, session_id: UUID) -> list[dict[str, str]]:
        """Build conversation context from session history.
        
        Retrieves the most recent messages from the session and
        formats them as a list of dictionaries with 'role' and
        'content' keys.
        
        Args:
            session_id: UUID of the chat session
            
        Returns:
            List of message dicts in chronological order:
            [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
        """
        # Get messages ordered by most recent first, then reverse
        messages = ChatMessage.query.filter_by(session_id=session_id)\
            .order_by(ChatMessage.created_at.desc())\
            .limit(self._max_pairs * 2)\
            .all()
        
        # Reverse to get chronological order
        messages = list(reversed(messages))
        
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

    def build_context_with_metadata(
        self,
        session_id: UUID
    ) -> list[dict[str, Any]]:
        """Build conversation context including message metadata.
        
        Similar to build_context but includes metadata for each
        assistant message (e.g., generated SQL, confidence scores).
        
        Args:
            session_id: UUID of the chat session
            
        Returns:
            List of message dicts with optional metadata:
            [{"role": "user", "content": "...", "metadata": None}, ...]
        """
        messages = ChatMessage.query.filter_by(session_id=session_id)\
            .order_by(ChatMessage.created_at.desc())\
            .limit(self._max_pairs * 2)\
            .all()
        
        messages = list(reversed(messages))
        
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "metadata": msg.metadata_json
            }
            for msg in messages
        ]

    def get_context_size(self, session_id: UUID) -> int:
        """Get the number of messages in session history.
        
        Args:
            session_id: UUID of the chat session
            
        Returns:
            Total message count in the session
        """
        return ChatMessage.query.filter_by(session_id=session_id).count()

    def truncate_context_if_needed(
        self,
        context: list[dict[str, str]],
        max_tokens: int = 4000
    ) -> list[dict[str, str]]:
        """Truncate context to fit within token limits.
        
        Estimates token count and removes oldest messages if needed.
        Uses a rough estimate of 4 characters per token.
        
        Args:
            context: List of message dicts
            max_tokens: Maximum allowed tokens
            
        Returns:
            Possibly truncated context list
        """
        # Rough estimate: 4 chars per token
        chars_per_token = 4
        max_chars = max_tokens * chars_per_token
        
        total_chars = sum(len(msg["content"]) for msg in context)
        
        if total_chars <= max_chars:
            return context
        
        # Remove oldest messages until under limit
        truncated = list(context)
        while truncated and total_chars > max_chars:
            removed = truncated.pop(0)
            total_chars -= len(removed["content"])
        
        return truncated


# Default instance
_context_builder: ContextBuilder | None = None


def get_context_builder() -> ContextBuilder:
    """Get or create the default context builder instance.
    
    Returns:
        ContextBuilder instance
    """
    global _context_builder
    if _context_builder is None:
        _context_builder = ContextBuilder()
    return _context_builder
