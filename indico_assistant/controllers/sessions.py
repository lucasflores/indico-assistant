"""Session management endpoint controllers.

Handles session listing, detail view, and deletion.

Feature: 004-chat-api
Tasks: T023, T024, T025
"""

from __future__ import annotations

import logging
from uuid import UUID

from flask import jsonify, request

from indico_assistant.controllers.base import RHChatBase
from indico_assistant.models.session import ChatSession
from indico_assistant.schemas.session import (
    MessageItem,
    SessionDetailResponse,
    SessionListItem,
    SessionListResponse,
)
from indico_assistant.services.chat import (
    get_session_manager,
    jobs,
)
from indico_assistant.services.chat.session_manager import InvalidCursor

logger = logging.getLogger(__name__)


class RHSessionList(RHChatBase):
    """Request handler for GET /sessions endpoint.
    
    Lists all chat sessions for the authenticated user with pagination.
    """

    RATE_LIMIT = "read"

    def _process(self):
        """List user's chat sessions.
        
        Query Parameters:
            limit: Max items per page (default 20, max 100)
            offset: Items to skip (default 0)
            
        Returns:
            JSON response with paginated session list
        """
        # Parse pagination parameters
        try:
            limit = int(request.args.get("limit", 20))
            offset = int(request.args.get("offset", 0))
        except ValueError:
            return self._error_response(
                "VALIDATION_ERROR",
                "Invalid pagination parameters",
                status=422
            )
        
        # Validate pagination bounds
        if limit < 1 or limit > 100:
            return self._error_response(
                "VALIDATION_ERROR",
                "Limit must be between 1 and 100",
                status=422
            )
        
        if offset < 0:
            return self._error_response(
                "VALIDATION_ERROR",
                "Offset must be non-negative",
                status=422
            )
        
        cursor = request.args.get("cursor") or None
        search = (request.args.get("search") or "").strip() or None
        try:
            session_manager = get_session_manager()
            if cursor or not offset:
                # keyset pages, newest activity first (spec 020 R12); offset stays for old clients
                sessions, next_cursor = session_manager.page_sessions(self.user.id, limit, cursor, search)
            else:  # (the same conversations, in the same order: review, PR #5)
                sessions = (session_manager.listed(self.user.id, search)
                            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
                            .offset(offset).limit(limit).all())
                next_cursor = None
            # counted for the first page and offset pages only: a search is an unindexed ILIKE, and Past Chats
            # pages by cursor without reading it (review, PR #5)
            total = None if cursor else session_manager.listed(self.user.id, search).count()

            summaries = session_manager.summaries(sessions)
            items = []
            for session in sessions:
                message_count, last_message_at, title = summaries[session.id]
                items.append(SessionListItem(
                    session_id=str(session.id),
                    event_id=session.event_id,
                    created_at=session.created_at.isoformat(),
                    last_message_at=(last_message_at or session.updated_at).isoformat(),
                    message_count=message_count,
                    title=title,
                    updated_at=session.updated_at.isoformat(),
                ))

            response = SessionListResponse(
                sessions=items,
                total=total,
                limit=limit,
                offset=offset,
                next_cursor=next_cursor,
            )

            return jsonify(response.model_dump(mode='json')), 200

        except InvalidCursor:
            return self._error_response("VALIDATION_ERROR", "Invalid cursor", status=422)
        except Exception as e:
            logger.exception("Error listing sessions")
            return self._error_response(
                "INTERNAL_ERROR",
                "Failed to retrieve sessions",
                status=500
            )


class RHSessionDetail(RHChatBase):
    """Request handler for GET /sessions/<id> endpoint.
    
    Retrieves a specific session with its message history.
    """

    RATE_LIMIT = "read"

    def _process(self, session_id: str | None = None):
        # Indico does not pass URL args to _process; this never worked through the real route
        session_id = session_id or request.view_args["session_id"]
        """Get session details with message history.
        
        Args:
            session_id: UUID of the session to retrieve
            
        Returns:
            JSON response with session details and messages
        """
        # Parse session_id
        try:
            uuid_id = UUID(session_id)
        except ValueError:
            return self._error_response(
                "VALIDATION_ERROR",
                "Invalid session_id format",
                status=422
            )
        
        try:
            session_manager = get_session_manager()
            
            # Get session
            session = session_manager.get_session(uuid_id)
            if not session:
                return self._error_response(
                    "SESSION_NOT_FOUND",
                    "Session not found",
                    status=404
                )
            
            # Validate ownership
            if not session_manager.validate_session_ownership(session, self.user.id):
                return self._error_response(
                    "ACCESS_DENIED",
                    "Session belongs to another user",
                    status=403
                )
            
            if request.args.get("messages") == "0":  # the panel only asks whether it is still there
                return jsonify({"session_id": str(session.id)}), 200

            # Get messages
            messages = session_manager.get_session_messages(uuid_id)
            feedback = session_manager.feedback_of([m.id for m in messages], self.user.id)

            # Build message items
            message_items = []
            for msg in messages:
                message_items.append(MessageItem(
                    message_id=str(msg.id),
                    role=msg.role,
                    content=msg.content,
                    created_at=msg.created_at.isoformat(),
                    # (msg.metadata is SQLAlchemy's table MetaData.) An answer's evidence is for the team's triage of a
                    # report only (spec 021 R5)
                    metadata={k: v for k, v in msg.metadata_json.items() if k != "evidence"}
                    if msg.metadata_json else msg.metadata_json,
                    feedback=feedback.get(msg.id),
                ))
            # an answer still being written when the user left: its job is on the question (spec 020 R9). Only
            # while it runs: a failed or expired job has no answer coming (review, PR #5: its error came back on
            # every page)
            last = messages[-1] if messages else None
            job_id = (last.metadata_json or {}).get("job_id") if last is not None and last.role == "user" else None
            pending = job_id if job_id and (jobs.get(job_id) or {}).get("status") == "pending" else None
            from indico_assistant.services.actions.executor import open_plan
            waiting = open_plan(session.id)

            response = SessionDetailResponse(
                session_id=str(session.id),
                event_id=session.event_id,
                created_at=session.created_at.isoformat(),
                updated_at=session.updated_at.isoformat(),
                title=session_manager.title_of(session),
                pending_job_id=pending,
                waiting_plan_id=str(waiting.id) if waiting else None,
                messages=message_items
            )
            
            return jsonify(response.model_dump(exclude_none=True, mode='json')), 200
            
        except Exception as e:
            logger.exception("Error retrieving session")
            return self._error_response(
                "INTERNAL_ERROR",
                "Failed to retrieve session",
                status=500
            )


class RHSessionDelete(RHChatBase):
    """Request handler for DELETE /sessions/<id> endpoint.
    
    Deletes a chat session and all its messages.
    """

    RATE_LIMIT = "chat"

    def _process(self, session_id: str | None = None):
        # Indico does not pass URL args to _process; this never worked through the real route
        session_id = session_id or request.view_args["session_id"]
        """Delete a chat session.
        
        Args:
            session_id: UUID of the session to delete
            
        Returns:
            204 No Content on success
        """
        # Parse session_id
        try:
            uuid_id = UUID(session_id)
        except ValueError:
            return self._error_response(
                "VALIDATION_ERROR",
                "Invalid session_id format",
                status=422
            )
        
        try:
            session_manager = get_session_manager()
            
            # Get session to validate ownership
            session = session_manager.get_session(uuid_id)
            if not session:
                return self._error_response(
                    "SESSION_NOT_FOUND",
                    "Session not found",
                    status=404
                )
            
            # Validate ownership
            if not session_manager.validate_session_ownership(session, self.user.id):
                return self._error_response(
                    "ACCESS_DENIED",
                    "Session belongs to another user",
                    status=403
                )
            
            # Delete session (cascade will delete messages and feedback)
            deleted = session_manager.delete_session(uuid_id)
            session_manager.commit()
            
            if deleted:
                return "", 204
            else:
                return self._error_response(
                    "SESSION_NOT_FOUND",
                    "Session not found",
                    status=404
                )
                
        except Exception as e:
            session_manager.rollback()
            logger.exception("Error deleting session")
            return self._error_response(
                "INTERNAL_ERROR",
                "Failed to delete session",
                status=500
            )


class RHSessionRename(RHChatBase):
    """PATCH /sessions/<id> {"title": "…"}: rename a conversation in the Past Chats sidebar (spec 020 US4)."""

    RATE_LIMIT = "read"

    TITLE_MAX = 200  # chat_sessions.title

    def _process(self):
        try:
            uuid_id = UUID(request.view_args["session_id"])
        except ValueError:
            return self._error_response("VALIDATION_ERROR", "Invalid session_id format", status=422)
        body = request.get_json(silent=True)
        body = body if isinstance(body, dict) else {}  # (a JSON array or string would fail .get)
        title = body.get("title").strip() if isinstance(body.get("title"), str) else ""
        if not title or len(title) > self.TITLE_MAX:
            return self._validation_error(f"A title of 1 to {self.TITLE_MAX} characters is required", field="title")
        session_manager = get_session_manager()
        session = session_manager.get_session(uuid_id)
        if session is None:
            return self._error_response("SESSION_NOT_FOUND", "Session not found", status=404)
        if not session_manager.validate_session_ownership(session, self.user.id):
            return self._error_response("ACCESS_DENIED", "Session belongs to another user", status=403)
        session_manager.rename(session, title)
        session_manager.commit()
        return jsonify(SessionListItem(
            session_id=str(session.id), event_id=session.event_id, created_at=session.created_at.isoformat(),
            last_message_at=(session.last_message_at or session.updated_at).isoformat(),
            message_count=session.message_count, title=session.title, updated_at=session.updated_at.isoformat(),
        ).model_dump(mode="json")), 200


class RHSessionOpen(RHChatBase):
    """PUT /sessions/<id> {"first_message": "…"}: the chat panel starts a conversation under its thread id before
    its first question is stored, so Past Chats can list it at once (spec 020). Creates it for the caller if it is
    missing (201), leaves the caller's own as it is (200); someone else's is refused (403)."""

    RATE_LIMIT = "read"

    def _process(self):
        try:
            uuid_id = UUID(request.view_args["session_id"])
        except ValueError:
            return self._error_response("VALIDATION_ERROR", "Invalid session_id format", status=422)
        body = request.get_json(silent=True)
        first_message = body.get("first_message") if isinstance(body, dict) else None
        session_manager = get_session_manager()
        session = session_manager.get_session(uuid_id)
        if session is not None:
            if not session_manager.validate_session_ownership(session, self.user.id):
                return self._error_response("ACCESS_DENIED", "Session belongs to another user", status=403)
            return jsonify({"session_id": str(session.id), "title": session_manager.title_of(session)}), 200
        title = session_manager.title_from(first_message if isinstance(first_message, str) else "") or None
        session = session_manager.create_session(self.user.id, None, session_id=uuid_id)
        if not session_manager.validate_session_ownership(session, self.user.id):
            return self._error_response("ACCESS_DENIED", "Session belongs to another user", status=403)
        if title and not session.title:
            session.title = title
        session_manager.commit()
        return jsonify({"session_id": str(session.id), "title": title or ""}), 201
