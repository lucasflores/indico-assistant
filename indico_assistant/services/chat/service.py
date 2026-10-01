"""Chat service orchestrator for processing user messages.

Coordinates the chat flow: session management, context building,
NL2SQL processing, and response generation.

Feature: 004-chat-api
Feature: 006-vector-search-rag (RAG integration T039, T040)
Feature: 016-user-id-passthrough (T009, T012, T019, T020)
Task: T015
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional
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
from indico_assistant.services.chat.citations import (
    CitationBuilder,
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
    plan: Optional[dict[str, Any]] = None  # Feature 019: a plan to confirm (PlanView, with its token)


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
    
    def __init__(self, message: str, reason: Optional[str] = None):
        self.reason = reason
        super().__init__(message)


class ChatService:
    """Orchestrates chat message processing.
    
    Coordinates between session management, context building, and
    the NL2SQL pipeline to process user messages and generate responses.
    """

    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        context_builder: Optional[ContextBuilder] = None
    ):
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
        session_id: Optional[UUID] = None,
        event_id: Optional[int] = None,
        uploads: Optional[list[dict[str, Any]]] = None,
        answer_id: Optional[UUID] = None
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
        # the page this question was sent from; a question from before spec 020 has the session's event
        event_id = (self._session_manager.page_event_of(message_id, session.event_id) if message_id
                    else session.event_id)
        self._validate_event_access(user, event_id)  # again: access may have been revoked while queued
        # plain values: touching expired ORM objects later would open a transaction mid-pipeline
        viewer = SimpleNamespace(id=user.id, is_admin=bool(user.is_admin))
        context = self._context_builder.build_context(session.id, up_to=message_id)
        if note := self._context_builder.page_note(event_id, user):
            # right before the question: earlier messages about other events are not "this event" (FR-009)
            at = len(context) - 1 if context and context[-1].get("role") == "user" else len(context)
            context = [*context[:at], note, *context[at:]]
        from indico_assistant.services.actions.executor import open_plan
        waiting_plan = open_plan(session.id)
        offer = self._session_manager.offer_before(session.id, message_id)  # the change the last answer offered
        db.session.commit()

        # Feature 019: a message about an open plan ("make it 30 minutes", "yes") goes to the planner first;
        # otherwise NL2SQL classifies it, and a change request goes to the planner (research R13)
        # Spec 022 (Lucas, 2026-09-30), in order: a plain yes to an offer plans the offered change (the offer is
        # newer than any waiting plan); a plain yes or no, or one of the plan's own choices, to a waiting plan goes
        # straight to the planner (but a plain no to an offer turns down the offer, not the plan); otherwise one Jev
        # decision gives the route and a data question's kind; without Jev the classifier routes, with the planner
        # first after an offer. A change the planner cannot plan gets the knowledge answer.
        # Spec 023: while GitHub is on, Jev (or the classifier) has a sixth route, connector.
        from indico_assistant.services.actions.planner import AFFIRMATIVE, NEGATIVE, exact_reply
        from indico_assistant.services.nl2sql.pipeline import OUT_OF_SCOPE_MESSAGE

        github_on = self._github_on()
        decision, fallback, planned, answer, open_for_change = None, None, None, None, waiting_plan
        request, tried = message, False  # what the knowledge answer is asked; whether the planner was already asked
        if offer and NEGATIVE.fullmatch(message):
            waiting_plan = open_for_change = None  # it turns down the offer: nothing may cancel the waiting plan
        if offer and AFFIRMATIVE.fullmatch(message):
            # the planner plans what was offered, as a new request (a bare yes has no plan to confirm)
            route, request, open_for_change = "change", offer, None
        elif exact_reply(waiting_plan, message):
            route = "change"
        else:
            decision = self._decide(context, plan_waiting=waiting_plan is not None, offer=offer, connector=github_on)
            route = decision.route
            if decision.skipped:  # no key, slow, or an error: the classifier routes, as before the router
                open_for_change = None  # (a change the classifier finds is a new request)
                if waiting_plan or offer:
                    planned = self._plan(user, session.id, message, context, waiting_plan, event_id, offer)
                    tried = waiting_plan is None  # (asked as a new request: asking again would give the same)
                    if planned is not None and waiting_plan is None and planned[1].get("cannot_plan"):
                        planned = None  # not a change after all: routed as if there had been no offer
                fallback = "planner first" if planned is not None else None  # (the classifier did not run)
                route = "change" if planned is not None else None
            if route in (None, "data"):
                if route is None or decision.intent is None:
                    fallback = "classifier"  # it routes, or (Jev's intent was not one of the 11) picks the kind
                response_text, metadata = self._process_with_nl2sql(
                    message, context, event_id, user_id=viewer.id, auth_user=viewer,
                    intent=decision.intent if route == "data" else None,
                    intent_confidence=decision.intent_confidence if route == "data" else None,
                    connector=github_on,
                )
                route = _route_of(metadata)
            elif route == "out_of_scope":  # (spec 021 R4: a refusal carries the report offer)
                route, response_text, metadata = "refusal", OUT_OF_SCOPE_MESSAGE, {"problem": "out_of_scope"}
        if route == "change" and planned is None:
            if not tried:
                planned = self._plan(user, session.id, message, context, open_for_change, event_id, offer)
            if planned is None or (planned[1].get("cannot_plan") and open_for_change is None):
                planned, route, fallback = None, "knowledge", ", ".join(filter(None, (fallback, "planner")))
        if route == "knowledge":  # (after an offer the planner could not plan: about the offer, not the "yes")
            answer = self._knowledge(user, request, context, event_id)
        elif route == "chat":
            answer = self._chat(message, context)
        elif route == "connector":  # (its own history: no Indico answers, no page note)
            answer = self._connector(user, message, self._context_builder.connector_history(session.id, up_to=message_id),
                                     started)
        plan = None
        if answer is not None:  # (a knowledge or chat answer that failed carries the report offer, spec 021 R4)
            response_text, metadata = answer.text, {"problem": "failed"} if answer.failed else {}
        elif planned is not None:
            response_text, metadata, plan = planned
        metadata = {**(metadata or {}), "route": _route_record(route, answer, decision=decision, fallback=fallback)}

        assistant_msg = self._session_manager.add_assistant_message(
            self._session_manager.get_session(session_id), response_text, metadata,
            message_id=self._session_manager.answer_id_of(message_id) if message_id else None,
        )
        self._session_manager.commit()
        return ChatResult(
            response=response_text,
            session_id=session_id,
            message_id=assistant_msg.id,
            metadata=metadata or {},
            plan=plan,
        )

    def _knowledge(self, user, message, context, page_event_id=None):
        """The knowledge answer (spec 022): the capability and page lists are built as the user, like the planner's
        permission checks; the model call itself needs no Indico state."""
        from indico.modules.events import Event

        from indico_assistant.plugin import AssistantPlugin
        from indico_assistant.services.actions.context import acting_as
        from indico_assistant.services.knowledge import answer as knowledge
        from indico_assistant.services.knowledge.capabilities import capability_list
        from indico_assistant.services.knowledge.guide import get_guide
        from indico_assistant.services.knowledge.pages import page_list

        plugin = AssistantPlugin.instance
        settings = plugin.settings.get_all()
        event = Event.get(page_event_id, is_deleted=False) if page_event_id else None
        try:
            with acting_as(user):
                caps, pages = capability_list(user, event, settings), page_list(user, event)
        except Exception:  # (another plugin's menu, a query): a plain message, never no reply at all
            logger.exception("Could not build the knowledge answer's lists")
            db.session.rollback()
            return knowledge.KnowledgeResult(knowledge.NOT_ANSWERED, failed=True)
        db.session.commit()  # plain lists now: no transaction stays open through the guide search and the model call
        return knowledge.answer(message, _history(context), llm=plugin.llm_service, caps=caps, pages=pages,
                                guide=get_guide(), base_url=self._get_base_url(),  # (Indico's own address)
                                event=event)

    def _plan(self, user, session_id, message, context, waiting_plan, page_event_id=None, offer=None):
        """The chat-action planner's answer, or None when the message turns out to be a question. ``offer``: the
        change the last answer offered, which a plain yes plans."""
        from indico_assistant.plugin import AssistantPlugin
        from indico_assistant.services.actions.context import acting_as
        from indico_assistant.services.actions.planner import plan_turn

        plugin = AssistantPlugin.instance
        with acting_as(user):  # resolving names and checking permissions reads Indico as the user
            turn = plan_turn(user, session_id, message, _history(context), waiting_plan, llm=plugin.llm_service,
                             settings=plugin.settings.get_all(), page_event_id=page_event_id, offer=offer)
        if not turn.handled:
            return None
        metadata = {"plan_id": turn.plan["id"] if turn.plan else None, "cannot_plan": turn.cannot_plan}
        if turn.problem:
            metadata["problem"] = turn.problem  # the chat offers a report under it (spec 021 R4)
        return turn.reply, metadata, turn.plan

    def _decide(self, context, plan_waiting=False, offer=None, connector=False):
        """Jev's route for the latest message; skipped (the classifier routes) without a key, slow, or on an error."""
        from indico_assistant.plugin import AssistantPlugin
        from indico_assistant.services.knowledge import gate

        try:
            settings = AssistantPlugin.instance.settings.get_all()
        except RuntimeError:  # the plugin is not active (tests, scripts): no key, so the classifier routes
            settings = {}
        return gate.decide(context, settings, plan_waiting=plan_waiting, offer=offer, connector=connector)

    def _chat(self, message, context):
        """The chat answer (spec 022): from the conversation, informed by general knowledge."""
        from indico_assistant.plugin import AssistantPlugin
        from indico_assistant.services.knowledge.chat import chat_answer

        return chat_answer(message, _history(context), llm=AssistantPlugin.instance.llm_service,
                           base_url=self._get_base_url())

    @staticmethod
    def _github_on():
        """Spec 023: whether the connector route is offered (an admin turned GitHub on)."""
        from indico_assistant.plugin import AssistantPlugin

        try:
            return bool(AssistantPlugin.instance.settings.get("github_enabled"))
        except RuntimeError:  # the plugin is not active (tests, scripts)
            return False

    def _connector(self, user, message, context, started=None):
        """The connector answer (spec 023): the user's GitHub, read with their own token."""
        from celery.exceptions import SoftTimeLimitExceeded
        from indico.core.plugins import url_for_plugin

        from indico_assistant.plugin import AssistantPlugin
        from indico_assistant.services.connectors.loop import ConnectorResult, answer
        from indico_assistant.services.knowledge.answer import NOT_ANSWERED

        plugin = AssistantPlugin.instance
        try:
            return answer(user.id, message, _history(context), llm=plugin.llm_service,
                          settings=plugin.settings.get_all(), base_url=self._get_base_url(),
                          profile_url=url_for_plugin("assistant.user_connections", _external=True), started=started)
        except SoftTimeLimitExceeded:  # (the task reports the timeout)
            raise
        except Exception:  # (an unexpected failure: a plain failed answer with the report offer, as _knowledge does)
            logger.exception("The connector answer failed")
            db.session.rollback()
            return ConnectorResult(NOT_ANSWERED, failed=True)

    def _get_or_create_session(
        self,
        session_id: Optional[UUID],
        user_id: int,
        event_id: Optional[int]
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
    def _load_user(user_id: Optional[int]):
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
                raise EventAccessDeniedError(
                    event_id,
                    "You do not have access to this event"
                )
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
            if hasattr(config, 'BASE_URL') and config.BASE_URL:
                return config.BASE_URL.rstrip('/')
        except (ImportError, AttributeError):
            pass
        
        try:
            # Fallback to plugin setting if configured
            from indico_assistant.plugin import AssistantPlugin
            plugin = AssistantPlugin.instance
            if plugin and hasattr(plugin, 'settings'):
                base_url = plugin.settings.get('base_url')
                if base_url:
                    return base_url.rstrip('/')
        except (ImportError, AttributeError, RuntimeError):
            pass
        
        return 'http://localhost:8000'

    def _generate_event_citations(self, event_ids: list[int]) -> list[str]:
        """Generate markdown citation links for event IDs.
        
        Feature: 015-chat-source-citations
        Task: T014
        
        Args:
            event_ids: List of event IDs to cite
            
        Returns:
            List of markdown citation links
        """
        if not event_ids:
            return []
        
        base_url = self._get_base_url()
        builder = CitationBuilder(base_url=base_url)
        
        citations = []
        for event_id in event_ids:
            citation = builder.build_event_citation(event_id)
            citations.append(citation)
        
        return citations

    def _extract_document_citations(self, search_results: list) -> list[dict]:
        """Extract document citation metadata from RAG search results.
        
        Feature: 015-chat-source-citations
        Task: T023
        
        Args:
            search_results: List of SearchResult objects from vector search
            
        Returns:
            List of citation metadata dicts with type, IDs, URL, description
        """
        if not search_results:
            return []
        
        base_url = self._get_base_url()
        builder = CitationBuilder(base_url=base_url)
        
        citations = []
        seen_files = set()  # Dedup by file_id
        
        for result in search_results:
            # Extract metadata (Feature 011: T004 ensures these are present)
            metadata = getattr(result, 'metadata', {}) or {}
            contribution_id = metadata.get('contribution_id')
            file_id = metadata.get('file_id')
            filename = metadata.get('filename', 'document')
            
            # Skip if missing required IDs or already seen
            if not contribution_id or not file_id or file_id in seen_files:
                continue
            
            seen_files.add(file_id)
            
            # Extract event_id and attachment_id
            event_id = getattr(result, 'event_id', None)
            attachment_id = metadata.get('attachment_id')
            
            # Skip if missing core identifiers
            if not event_id or not attachment_id:
                continue
            
            # Build citation URL
            citation_url = builder.build_document_url(
                event_id=event_id,
                contribution_id=contribution_id,
                attachment_id=attachment_id,
                file_id=file_id,
                filename=filename
            )
            
            citations.append({
                "type": "document",
                "event_id": event_id,
                "contribution_id": contribution_id,
                "attachment_id": attachment_id,
                "file_id": file_id,
                "filename": filename,
                "url": citation_url,
                "description": f"Document: {filename}"  # Feature 015: T030 - type-specific prefix
            })
        
        return citations

    def _process_with_nl2sql(
        self,
        message: str,
        context: list[dict[str, str]],
        event_id: Optional[int],
        user_id: Optional[int] = None,
        auth_user: Any = None,
        intent: str | None = None,
        intent_confidence: float | None = None,
        connector: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        """Process message through NL2SQL pipeline with RAG enhancement.

        ``intent``: the kind of data question when the router (Jev) decided it; the classifier is then skipped.
        
        Args:
            message: User's message
            context: Conversation history
            event_id: Event scope (optional)
            user_id: User ID for permission filtering (optional)
            
        Returns:
            Tuple of (response_text, metadata)
        """
        # Initialize metadata
        metadata: dict[str, Any] = {}
        
        try:
            from indico_assistant.plugin import AssistantPlugin
            from indico_assistant.services.nl2sql import create_nl2sql_pipeline_from_plugin
            from indico_assistant.services.nl2sql.models import PipelineErrorType

            plugin = AssistantPlugin.instance
            if not plugin:
                raise ImportError("Assistant plugin instance not available")

            pipeline = create_nl2sql_pipeline_from_plugin(plugin)

            logger.debug(
                "Executing NL2SQL pipeline",
                extra={"event_id": event_id, "user_id": user_id}
            )

            # Feature 016 (T009): Pass user_id as-is (can be None)
            # The pipeline now accepts user_id: int | None (T010)
            result = pipeline.process(
                question=message,
                user_id=user_id,
                user=auth_user,  # decides visibility (row-level security context)
                event_ids=[event_id] if event_id else None,
                conversation_history=context,  # Feature 012: T006
                **({"intent": intent, "intent_confidence": intent_confidence} if intent else {}),  # (routed by Jev)
                **({"connector": True} if connector else {}),  # (spec 023: GitHub is on)
            )

            response_text = result.answer or ""
            if not result.success:
                response_text = (
                    result.error.user_message
                    if result.error
                    else "Unable to process your query"
                )

            error_payload = None
            if result.error:
                error_payload = (
                    result.error.model_dump()
                    if hasattr(result.error, "model_dump")
                    else result.error.dict()
                )

            # Feature 015: Extract event IDs and generate citations (T013, T014)
            source_event_ids = getattr(result, 'source_event_ids', [])
            data_sources = []
            
            # Build citation metadata for event sources
            if source_event_ids:
                base_url = self._get_base_url()
                builder = CitationBuilder(base_url=base_url)
                
                for event_id in source_event_ids:
                    citation_url = builder.build_event_url(event_id)
                    data_sources.append({
                        "type": "event",
                        "event_id": event_id,
                        "url": citation_url,
                        "description": f"Event: {event_id}"  # Feature 015: T030 - type-specific prefix
                    })
            
            # Legacy fallback: include table names if no event sources
            if not data_sources and result.tables_accessed:
                data_sources = result.tables_accessed
            
            metadata.update({
                "sql_generated": result.generated_sql,
                "confidence": result.confidence,
                "data_sources": data_sources,  # Feature 015: New dict format
                "pipeline_success": result.success,
                "pipeline_error": error_payload,
                "suggested_followups": getattr(result, 'suggested_followups', []),
                "write_request": getattr(result, 'write_request', False),
                "knowledge_request": getattr(result, 'knowledge_request', False),
                "chat_request": getattr(result, 'chat_request', False),
                "connector_request": getattr(result, 'connector_request', False),
                # how the answer was made, for the team's triage of a report (spec 021 R5): recorded now, since the
                # query log has no link to answers. Never returned to the user (sessions API, job result)
                "evidence": {
                    "intent": result.intent,
                    "intent_confidence": result.intent_confidence,
                    "row_count": result.row_count,
                    "validation_rejection": result.validation_rejection,
                    "correction_attempts": result.correction_attempts,
                    "corrected": result.corrected,
                    "cached": result.from_cache,
                },
            })
            if not result.success:  # the chat offers a report under it (spec 021 R4)
                out_of_scope = result.error is not None and result.error.error_type == PipelineErrorType.OUT_OF_SCOPE
                metadata["problem"] = "out_of_scope" if out_of_scope else "failed"

            return response_text, metadata

        except ImportError:
            # NL2SQL service not available, return mock response
            logger.warning("NL2SQL service not available, returning mock response")
            response = (
                f"I received your message: '{message}'. "
                "The NL2SQL pipeline is not configured."
            )
            
            metadata["mock_response"] = True
            return response, metadata
            
        except Exception as e:
            logger.exception("NL2SQL processing failed")
            raise QueryProcessingError(
                "Unable to process your query",
                reason=str(e)
            ) from e


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


def _history(context):
    """The conversation before the question: the context ends with the question (a page note goes before it). For
    an accepted offer the planner is asked the offer instead, and the bare "yes" must not stay in its history."""
    return context[:-1] if context and context[-1].get("role") == "user" else context


def _route_of(metadata):
    """The route an NL2SQL pipeline result stands for (with the classifier, it routes as well as answers)."""
    if metadata.get("knowledge_request"):
        return "knowledge"
    if metadata.get("chat_request"):
        return "chat"
    if metadata.get("connector_request"):
        return "connector"
    if metadata.get("write_request"):
        return "change"
    error = metadata.get("pipeline_error") or {}
    return "refusal" if isinstance(error, dict) and error.get("error_type") == "out_of_scope" else "data"


def _route_record(route, answer=None, *, decision=None, fallback=None):
    """How this answer was reached (spec 022, FR-020): kept in its metadata, so routing can be audited on real
    traffic. ``decision`` is Jev's (None for the shortcut, when neither Jev nor the classifier was asked)."""
    return {
        "route": route,  # knowledge | chat | data | change | connector | refusal
        "jev": None if decision is None else {
            "route": decision.route, "intent": decision.intent, "confidence": decision.confidence,
            "skipped": decision.skipped, "reason": decision.reason, "ms": decision.ms, "model": decision.name,
        },
        "shortcut": decision is None,
        "fallback": fallback,  # classifier | planner | "classifier, planner" | "planner first" (without Jev, after
                               # an offer or with a plan waiting: the planner took it, the classifier did not run)
        "offer": answer.offer if answer else None,
        "guide_commit": answer.guide_commit if answer else None,
        "failed": bool(answer.failed) if answer else False,
        "tools": getattr(answer, "tools", None),  # the connector's calls: {name, ms, ok}, never what they read
    }
