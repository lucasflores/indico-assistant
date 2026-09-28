"""Chat endpoint controller.

Handles POST /chat requests for conversational queries.

Feature: 004-chat-api
Feature: 016-user-id-passthrough (T024)
Task: T017
"""

from __future__ import annotations

import logging

from flask import jsonify, request
from pydantic import ValidationError

from indico_assistant.controllers.base import RHChatBase
from indico_assistant.schemas.chat import ChatRequest, ChatResponse
from indico_assistant.services.chat import (
    EventAccessDeniedError,
    SessionAccessDeniedError,
    SessionNotFoundError,
    get_chat_service,
    jobs,
)
from indico_assistant.services.chat.rate_limiter import (
    get_rate_limiter,
)

logger = logging.getLogger(__name__)

RESPONSE_METADATA = ("sql_generated", "confidence", "data_sources", "suggested_followups")


class RHChat(RHChatBase):
    """POST /chat: save the message and queue its answer (Celery); poll RHChatJob for the reply."""

    def _check_access(self) -> None:
        super()._check_access()  # login required
        rate_result = get_rate_limiter().check_rate(self.user.id, "chat")
        if not rate_result.allowed:
            raise self._rate_limit_error(rate_result.retry_after)

    def _process(self):
        """Process the chat request.
        
        Returns:
            JSON response with assistant message and metadata
        """
        # Parse and validate request
        try:
            data = request.get_json()
            if not data:
                return self._error_response(
                    "VALIDATION_ERROR",
                    "Request body is required",
                    status=422
                )
            
            chat_request = ChatRequest.model_validate(data)
        except ValidationError as e:
            return self._validation_error(str(e))
        except Exception as e:
            logger.warning("Failed to parse request body: %s", e)
            return self._error_response(
                "VALIDATION_ERROR",
                "Invalid request body",
                status=422
            )

        try:
            session_id, created, message_id = get_chat_service().submit_message(
                user=self.user,
                message=chat_request.message,
                session_id=chat_request.session_id,
                event_id=chat_request.event_id,
            )
        except SessionNotFoundError:
            return self._error_response("SESSION_NOT_FOUND", "Session not found", status=404)
        except SessionAccessDeniedError:
            return self._error_response("ACCESS_DENIED", "Session belongs to another user", status=403)
        except EventAccessDeniedError as e:
            return self._error_response("ACCESS_DENIED", f"Access denied to event {e.event_id}", status=403)

        from indico_assistant.tasks.chat import answer_chat

        job_id = jobs.create(self.user.id, session_id)
        try:
            answer_chat.delay(job_id, self.user.id, session_id, chat_request.message, message_id)
        except Exception:
            # the message is saved; the answer never queued
            logger.exception("Could not queue chat answer %s", job_id)
            jobs.finish(job_id, status="failed", error="QUEUE_UNAVAILABLE", message="The assistant is busy")
            return self._error_response("QUEUE_UNAVAILABLE", "The assistant is unavailable, try again shortly",
                                        status=503)
        return jsonify({
            "job_id": job_id,
            "session_id": str(session_id),
            "created_session": created,
            "status": "pending",
        }), 202


class RHChatJob(RHChatBase):
    """GET /chat/jobs/<job_id>: the queued answer, once a worker has produced it."""

    def _check_access(self) -> None:
        super()._check_access()
        rate_result = get_rate_limiter().check_rate(self.user.id, "read")  # clients poll this
        if not rate_result.allowed:
            raise self._rate_limit_error(rate_result.retry_after)

    def _process(self):
        job = jobs.get(request.view_args["job_id"])
        if job is None or job.get("user_id") != self.user.id:
            return self._error_response("NOT_FOUND", "Unknown or expired chat job", status=404)
        if job["status"] == "pending":
            return jsonify({"status": "pending", "session_id": job["session_id"]}), 202
        if job["status"] == "failed":
            error = job.get("error", "INTERNAL_ERROR")
            status = {"ACCESS_DENIED": 403, "TIMEOUT": 504, "QUEUE_UNAVAILABLE": 503}.get(error, 500)
            return self._error_response(error, job.get("message", ""), status=status)
        metadata = job.get("metadata") or {}
        response = ChatResponse(
            session_id=job["session_id"],
            message_id=job["message_id"],
            response=job["response"],
            metadata={k: metadata.get(k) for k in RESPONSE_METADATA if metadata.get(k) is not None},
            plan=job.get("plan"),
        )
        return jsonify({"status": "done", **response.model_dump(exclude_none=True, mode="json")}), 200
