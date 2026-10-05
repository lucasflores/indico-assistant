"""Chat service orchestrator for processing user messages.

Coordinates the chat flow: session management, context building,
NL2SQL processing, and response generation.

Feature: 004-chat-api
Feature: 025-assistant-core (one way in: services/turn)
Feature: 016-user-id-passthrough (T009, T012, T019, T020)
Task: T015
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from indico.core.db import db

from indico_assistant.models.session import ChatSession
from indico_assistant.services.chat.context_builder import (
    ContextBuilder,
    get_context_builder,
)
from indico_assistant.services.chat.session_manager import (
    SessionManager,
    get_session_manager,
)

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    """Result of processing a chat message.

    Attributes:
        response: Assistant's response text
        session_id: Session UUID
        message_id: Assistant message UUID
        metadata: Response metadata (SQL, confidence, sources)
        created_session: Whether a new session was created
    """

    response: str
    session_id: UUID
    message_id: UUID
    metadata: dict[str, Any]
    created_session: bool = False
    plan: dict[str, Any] | None = None  # Feature 019: a plan to confirm (PlanView, with its token)


class ChatServiceError(Exception):
    """Base exception for chat service errors."""

    pass


class SessionNotFoundError(ChatServiceError):
    """Raised when a session is not found."""

    pass


class SessionAccessDeniedError(ChatServiceError):
    """Raised when user doesn't own the session."""

    pass


class EventAccessDeniedError(ChatServiceError):
    """Raised when user doesn't have access to the event."""

    def __init__(self, event_id: int, message: str = "Access denied"):
        self.event_id = event_id
        super().__init__(message)


class QueryProcessingError(ChatServiceError):
    """Raised when NL2SQL processing fails."""

    def __init__(self, message: str, reason: str | None = None):
        self.reason = reason
        super().__init__(message)


class ChatService:
    """Orchestrates chat message processing.

    Coordinates between session management, context building, and
    the NL2SQL pipeline to process user messages and generate responses.
    """

    def __init__(self, session_manager: SessionManager | None = None, context_builder: ContextBuilder | None = None):
        """Initialize the chat service.

        Args:
            session_manager: Custom session manager (optional)
            context_builder: Custom context builder (optional)
        """
        self._session_manager = session_manager or get_session_manager()
        self._context_builder = context_builder or get_context_builder()

    def submit_message(
        self,
        user: Any,
        message: str,
        session_id: UUID | None = None,
        event_id: int | None = None,
        uploads: list[dict[str, Any]] | None = None,
        answer_id: UUID | None = None,
    ) -> tuple[UUID, bool, UUID]:
        """Web-request half: check access, save the user's message, commit.

        Returns (session_id, created, message_id); the answer is bound to that message.

        The answer is produced by :meth:`answer` in a Celery worker, so no LLM call runs in the web tier.

        Raises:
            SessionNotFoundError: If session_id provided but not found
            SessionAccessDeniedError: If user doesn't own the session
            EventAccessDeniedError: If user can't access the event
        """
        try:
            session, created = self._get_or_create_session(session_id, user.id, event_id)
            # "this event" is the page the message is sent from (spec 020 R8): checked, and kept on the message
            self._validate_event_access(user, event_id)
            metadata: dict[str, Any] = {"event_id": event_id}
            if uploads:
                metadata["uploads"] = uploads
            if answer_id:
                metadata["answer_id"] = str(answer_id)
            user_message = self._session_manager.add_user_message(session, message, metadata)
            self._session_manager.commit()
            return session.id, created, user_message.id
        except Exception:
            self._session_manager.rollback()
            raise

    def record_job(self, message_id: UUID, job_id: str) -> None:
        """Keep the answer's job on the question: if the user navigates before the answer comes, the panel
        finds it again and waits for it (spec 020 R9)."""
        self._session_manager.set_message_metadata(message_id, job_id=job_id)
        self._session_manager.commit()

    def answer(self, user_id: int, session_id: UUID, message: str, message_id: UUID | None = None) -> ChatResult:
        """Worker half: answer one message of a session and save the reply.

        The context stops at ``message_id``: a question sent while this one was queued is not part of it.

        No database transaction stays open during the LLM calls: everything the pipeline needs is read
        first and committed, and the reply is written in a new short transaction.
        """
        import time

        started = time.monotonic()  # (the connector's budget counts from here, spec 023)
        session = self._session_manager.get_session(session_id)
        user = self._load_user(user_id)
        if session is None or user is None:
            raise SessionNotFoundError(f"Session {session_id} not found")
        from indico_assistant.services.analytics import recorder

        if self._session_manager.holds_connector_answer(session.id):
            recorder.private()  # an earlier GitHub answer is in every prompt of this chat (spec 024 FR-009)
        # the page this question was sent from; a question from before spec 020 has the session's event
        event_id = self._session_manager.page_event_of(message_id, session.event_id) if message_id else session.event_id
        self._validate_event_access(user, event_id)  # again: access may have been revoked while queued
        context = self._context_builder.build_context(session.id, up_to=message_id)
        if note := self._context_builder.page_note(event_id, user):
            # right before the question: earlier messages about other events are not "this event" (FR-009)
            at = len(context) - 1 if context and context[-1].get("role") == "user" else len(context)
            context = [*context[:at], note, *context[at:]]
        from indico_assistant.services.actions.executor import open_plan

        waiting_plan = open_plan(session.id)
        offer = self._session_manager.offer_before(session.id, message_id)  # the change the last answer offered
        db.session.commit()

        # Spec 025: one way in. The plan shortcuts of spec 019/022 first: a plain yes to an offer plans the offered
        # change; a plain yes or no, or one of the plan's own choices, to a waiting plan goes to the planner. Then the
        # turn: Jev's fast path for chat and unrelated messages, else the agent with its tools (services/turn).
        from indico.modules.events import Event

        from indico_assistant.services.actions.planner import AFFIRMATIVE, NEGATIVE, exact_reply
        from indico_assistant.services.turn import answer as turn
        from indico_assistant.services.turn.abilities import plan as plan_change

        event = Event.get(event_id, is_deleted=False) if event_id else None
        history = turn._history(context)
        planned, outcome, plan = None, None, None
        if turn.disabled_for(event):
            route, response_text, metadata = "disabled", turn.DISABLED, {}
        else:
            if offer and AFFIRMATIVE.fullmatch(message):
                planned = plan_change(user, session.id, message, history, None, event_id, offer)
            elif exact_reply(waiting_plan, message):
                planned = plan_change(user, session.id, message, history, waiting_plan, event_id, offer)
            if planned is not None and planned[1].get("cannot_plan") and waiting_plan is None:
                planned = None  # (the offer can't be planned after all: the turn answers the message)
            if planned is not None:
                route, (response_text, metadata, plan) = "change", planned
            else:
                if offer and NEGATIVE.fullmatch(message):
                    waiting_plan = None  # it turns down the offer: nothing may cancel the waiting plan
                outcome = turn.answer(
                    user,
                    session.id,
                    message,
                    message_id,
                    context,
                    event_id,
                    waiting_plan=waiting_plan,
                    offer=offer,
                    started=started,
                    github_on=self._github_on(),
                )
                route, response_text, metadata, plan = outcome.route, outcome.text, outcome.metadata, outcome.plan
        metadata = {**(metadata or {}), "route": _route_record(route, outcome)}

        assistant_msg = self._session_manager.add_assistant_message(
            self._session_manager.get_session(session_id),
            response_text,
            metadata,
            message_id=self._session_manager.answer_id_of(message_id) if message_id else None,
        )
        _link_answer(assistant_msg.id)  # (in the answer's own transaction: a vote always finds its turn)
        self._session_manager.commit()
        _record_turn(assistant_msg.id, route, outcome, metadata, plan)
        return ChatResult(
            response=response_text,
            session_id=session_id,
            message_id=assistant_msg.id,
            metadata=metadata or {},
            plan=plan,
        )

    @staticmethod
    def _github_on():
        """Spec 023: whether the connector route is offered (an admin turned GitHub on)."""
        from indico_assistant.plugin import AssistantPlugin

        try:
            return bool(AssistantPlugin.instance.settings.get("github_enabled"))
        except RuntimeError:  # the plugin is not active (tests, scripts)
            return False

    def _get_or_create_session(
        self, session_id: UUID | None, user_id: int, event_id: int | None
    ) -> tuple[ChatSession, bool]:
        """Get existing session or create new one.

        Args:
            session_id: Existing session UUID (optional)
            user_id: User ID
            event_id: Event scope (optional)

        Returns:
            Tuple of (session, created_flag)

        A ``session_id`` that does not exist yet starts a session under that id: the chat panel's thread id
        (spec 020 R5). One that exists must be the user's.

        Raises:
            SessionAccessDeniedError: If user doesn't own session
        """
        if session_id:
            session = self._session_manager.get_session(session_id)
            if not session:
                session = self._session_manager.create_session(user_id, event_id, session_id=session_id)
                if not self._session_manager.validate_session_ownership(session, user_id):
                    raise SessionAccessDeniedError("Session belongs to another user")  # (created meanwhile by another)
                return session, True

            if not self._session_manager.validate_session_ownership(session, user_id):
                raise SessionAccessDeniedError("Session belongs to another user")
            # (a conversation spans pages: each message carries its own event, spec 020 R8)
            if session.event_id is None and event_id is not None and not session.messages.count():
                # opened by the panel before its first question (PUT /sessions/<id>): it started on this page
                # (review, PR #5: panel conversations had no event). Access is checked by the caller.
                session.event_id = event_id
            return session, False

        # Create new session
        session = self._session_manager.create_session(user_id, event_id)
        return session, True

    @staticmethod
    def _load_user(user_id: int | None):
        if user_id is None:
            return None
        from indico.modules.users import User

        return User.get(user_id, is_deleted=False)

    def _validate_event_access(self, user, event_id: int) -> None:
        """Validate the authenticated user can access the event (Indico's own can_access).

        Raises:
            EventAccessDeniedError: If user can't access event
        """
        if event_id is None:
            return  # No event scoping, no validation needed

        try:
            from indico.modules.events import Event

            event = Event.get(event_id, is_deleted=False)
            if not event:
                raise EventAccessDeniedError(event_id, "Event not found")

            # user comes from the Indico session OR the Chainlit token (flask's session.user is None
            # for token requests, which made this check deny every Chainlit user before)
            if user is None or not event.can_access(user):
                raise EventAccessDeniedError(event_id, "You do not have access to this event")
        except ImportError:
            # If Indico modules not available (testing), skip validation
            logger.warning("Indico event module not available, skipping access check")

    def _get_base_url(self) -> str:
        """Get base URL for citation links from Indico config.

        Feature: 015-chat-source-citations
        Task: T012

        Returns:
            Base URL from Indico config (e.g., 'http://127.0.0.1:8000')
        """
        try:
            # Get from Indico's config (the actual instance URL)
            from indico.core.config import config

            if hasattr(config, "BASE_URL") and config.BASE_URL:
                return config.BASE_URL.rstrip("/")
        except (ImportError, AttributeError):
            pass

        try:
            # Fallback to plugin setting if configured
            from indico_assistant.plugin import AssistantPlugin

            plugin = AssistantPlugin.instance
            if plugin and hasattr(plugin, "settings"):
                base_url = plugin.settings.get("base_url")
                if base_url:
                    return base_url.rstrip("/")
        except (ImportError, AttributeError, RuntimeError):
            pass

        return "http://localhost:8000"


# Default instance
_chat_service: ChatService | None = None


def get_chat_service() -> ChatService:
    """Get or create the default chat service instance.

    Returns:
        ChatService instance
    """
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service


def _link_answer(answer_id):
    try:
        from indico_assistant.services.analytics import recorder

        recorder.link_answer(answer_id)
    except Exception:  # (the analytics never fail an answer, FR-006)
        logger.exception("Analytics: could not link this answer to its turn")


def _record_turn(answer_id, route, outcome, metadata, plan):
    """What the analytics keep of this answer (spec 024): stamped now, never recomputed. The outcome is set here for
    the answers that aren't plain answers (the task's default is "answered")."""
    try:
        _describe_turn(answer_id, route, outcome, metadata, plan)
    except Exception:  # (the analytics never fail an answer, FR-006)
        logger.exception("Analytics: could not describe this turn")


def _describe_turn(answer_id, route, outcome, metadata, plan):
    from indico_assistant.services.analytics import recorder

    decision = outcome.decision if outcome is not None else None
    result = outcome.result if outcome is not None else None
    extras = {"jev_probabilities": decision.probabilities} if decision is not None and decision.probabilities else {}
    if getattr(result, "stop", None):
        extras["turn_stop"] = result.stop
    queries = (metadata.get("evidence") or {}).get("queries") or []
    recorder.update(
        answer_id=answer_id,
        route=route,
        decided_by=(
            "shortcut" if outcome is None else "jev" if decision is not None and not decision.skipped else "none"
        ),
        jev_confidence=decision.confidence if decision is not None and not decision.skipped else None,
        intent=queries[-1].get("intent") if queries else None,
        corrections=sum(q.get("corrections") or 0 for q in queries) if queries else None,
        row_count=queries[-1].get("row_count") if queries else None,
        plan_id=_uuid(plan["id"]) if plan else None,
        tool_calls=len(outcome.tools) if outcome is not None and route == "agent" else None,
        record={"route": metadata["route"], **extras},
    )
    problem = metadata.get("problem")
    if route == "fast:out_of_scope" or problem == "out_of_scope":
        recorder.set_outcome("refusal")
    elif metadata.get("cannot_plan") or problem in ("cannot_do", "not_understood"):
        recorder.set_outcome("cannot_plan")
    elif problem == "failed":  # an answer saved as a failure ("I couldn't…") is not answered
        recorder.set_outcome(
            "failed", "unavailable" if getattr(result, "stop", None) == "unavailable" else "model_error"
        )


def _uuid(value):
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _route_record(route, outcome=None):
    """How this answer was reached (spec 022 FR-020, spec 025): kept in its metadata, so routing can be audited on
    real traffic. ``outcome`` is the turn's (None for a plan shortcut, when Jev wasn't asked)."""
    decision = outcome.decision if outcome is not None else None
    result = outcome.result if outcome is not None else None
    return {
        "route": route,  # fast:chat | fast:out_of_scope | agent | change (a plan shortcut) | disabled
        "jev": (
            None
            if decision is None
            else {
                "route": decision.route,
                "intent": decision.intent,
                "confidence": decision.confidence,
                "skipped": decision.skipped,
                "reason": decision.reason,
                "ms": decision.ms,
                "model": decision.name,
            }
        ),
        "shortcut": outcome is None,
        "offer": outcome.offer if outcome is not None else None,
        "failed": bool(getattr(result, "failed", False)),
        "tools": [t["name"] for t in outcome.tools] if outcome is not None and route == "agent" else None,
        "tool_calls": outcome.tools if outcome is not None and route == "agent" else None,
        "stop": getattr(result, "stop", None),
        "private": bool(outcome is not None and outcome.private),  # GitHub was read (spec 023/024)
    }
