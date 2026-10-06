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


#: An Indico answer's place in the connector's history: the turns still alternate, and the model knows one is missing
#: (fresh-review: some providers refuse two user turns in a row).
HIDDEN = "(An answer about Indico, not shown here.)"


def _github(msg):
    """An answer that read GitHub: the connector route's (spec 023), or a turn that called a GitHub tool (spec 025)."""
    route = (msg.metadata_json or {}).get("route") or {}
    return route.get("route") == "connector" or bool(route.get("private"))


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

    def build_context(self, session_id: UUID, up_to: UUID | None = None) -> list[dict[str, str]]:
        """Build conversation context from session history.
        
        Retrieves the most recent messages from the session and
        formats them as a list of dictionaries with 'role' and
        'content' keys.
        
        Args:
            session_id: UUID of the chat session
            up_to: Only messages up to and including this one (default: all)

        Returns:
            List of message dicts in chronological order:
            [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
        """
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self._recent(session_id, up_to)
        ]

    def connector_history(self, session_id: UUID, up_to: UUID | None = None) -> list[dict[str, str]]:
        """The conversation as the connector's loop may see it (spec 023: no Indico data in the loop; Copilot, PR
        #17): the user's own messages, and only the answers that came from GitHub. Never Indico's answers, nor the
        page note."""
        return [
            {"role": msg.role, "content": msg.content if msg.role == "user" or _github(msg) else HIDDEN}
            for msg in self._recent(session_id, up_to) if msg.role in ("user", "assistant")
        ]

    def _recent(self, session_id: UUID, up_to: UUID | None = None) -> list:
        """The latest messages, oldest first, up to and including ``up_to``."""
        query = ChatMessage.query.filter_by(session_id=session_id)
        if up_to is not None:
            query = query.filter(ChatMessage.created_at <= ChatMessage.query.with_entities(ChatMessage.created_at)
                                 .filter_by(id=up_to).scalar_subquery())
        messages = query.order_by(ChatMessage.created_at.desc()).limit(self._max_pairs * 2).all()
        return list(reversed(messages))

    def page_note(self, event_id: int | None, user: Any) -> dict[str, str]:
        """Which page the user is on now, for the model (spec 020 FR-009): one conversation spans pages, so
        earlier messages about other events must not be taken as "this event". The id only: seen live, a title
        here made the SQL generator search for it by keyword (and match its namesakes) instead of :event_id."""
        if event_id is None:
            return {"role": "system", "content": "The user is not on an event page now."}
        return {"role": "system",
                "content": f"The user is on the page of event {event_id} now: “this event” and “this meeting” "
                           f"mean that event (:event_id), not the events of earlier messages."}

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
