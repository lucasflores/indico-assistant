"""Plan endpoints: read, confirm, cancel (contracts/api.md).

Feature: 019-chat-actions

Chainlit's buttons send whatever the browser holds, so every call checks the owner, the token and the
plan's state here; the confirm itself is one atomic status change (a double click runs the plan once).
"""

from __future__ import annotations

import logging
from uuid import UUID

from flask import jsonify, request
from pydantic import ValidationError

from indico.core.db import db

from indico_assistant.controllers.base import RHChatBase
from indico_assistant.models import ActionPlan
from indico_assistant.schemas.actions import ConfirmRequest, PlanView
from indico_assistant.services.actions import enabled_actions, executor
from indico_assistant.services.chat import jobs
from indico_assistant.services.chat.rate_limiter import get_rate_limiter


logger = logging.getLogger(__name__)


class RHPlanBase(RHChatBase):
    def _check_access(self) -> None:
        super()._check_access()
        rate_result = get_rate_limiter().check_rate(self.user.id, "read")  # carrying out a plan is not a new question
        if not rate_result.allowed:
            raise self._rate_limit_error(rate_result.retry_after)

    def _plan(self):
        try:
            plan_id = UUID(request.view_args["plan_id"])
        except ValueError:
            return None
        return ActionPlan.query.filter_by(id=plan_id, user_id=self.user.id).first()

    def _not_found(self):
        return self._error_response("NOT_FOUND", "Unknown plan", status=404)


class RHPlan(RHPlanBase):
    """GET /plans/<plan_id>"""

    def _process(self):
        if (plan := self._plan()) is None:
            return self._not_found()
        return jsonify(PlanView.of(plan).model_dump(mode="json", exclude={"token"})), 200


class RHPlanConfirm(RHPlanBase):
    """POST /plans/<plan_id>/confirm: queue the plan to be carried out as the user."""

    def _process(self):
        if not enabled_actions(self.plugin.settings.get_all()):
            return self._error_response("ACTIONS_DISABLED", "Chat actions are switched off", status=403)
        try:
            body = ConfirmRequest.model_validate(request.get_json(silent=True) or {})
        except ValidationError:
            return self._validation_error("A confirm token is required", field="token")
        if (plan := self._plan()) is None:
            return self._not_found()
        outcome = executor.confirm(plan.id, self.user, body.token)
        if outcome == "invalid_token":
            return self._error_response("INVALID_TOKEN", "This is not the current version of the plan", status=403)
        if outcome != "confirmed":
            return self._error_response("PLAN_NOT_CONFIRMABLE", "This plan changed, expired or was already confirmed",
                                        details={"status": ActionPlan.query.get(plan.id).effective_status},
                                        status=409)
        job_id = jobs.create(self.user.id, plan.session_id)
        db.session.commit()  # the worker must see the confirmation
        from indico_assistant.tasks.actions import execute_plan

        try:
            execute_plan.delay(job_id, plan.id)
        except Exception:
            logger.exception("Could not queue plan %s", plan.id)
            ActionPlan.query.filter_by(id=plan.id, status="confirmed").update({"status": "shown"})
            db.session.commit()  # confirmable again once the queue is back
            jobs.finish(job_id, status="failed", error="QUEUE_UNAVAILABLE", message="The assistant is busy")
            return self._error_response("QUEUE_UNAVAILABLE", "The assistant is unavailable, try again shortly",
                                        status=503)
        return jsonify({"job_id": job_id, "plan_id": str(plan.id), "status": "confirmed"}), 202


class RHPlanToken(RHPlanBase):
    """POST /plans/<plan_id>/token: the plan card drawn again after navigating (spec 020 R10)."""

    def _process(self):
        if (plan := self._plan()) is None:
            return self._not_found()
        if (token := executor.reissue_token(plan.id, self.user)) is None:
            return self._error_response("PLAN_NOT_CONFIRMABLE", "This plan is no longer waiting for an answer",
                                        details={"status": ActionPlan.query.get(plan.id).effective_status},
                                        status=409)
        db.session.commit()
        return jsonify(PlanView.of(ActionPlan.query.get(plan.id), token).model_dump(mode="json")), 200


class RHPlanCancel(RHPlanBase):
    """POST /plans/<plan_id>/cancel"""

    def _process(self):
        if (plan := self._plan()) is None:
            return self._not_found()
        if not executor.cancel(plan.id, self.user):
            return self._error_response("PLAN_NOT_CANCELLABLE", "This plan is no longer waiting for an answer",
                                        details={"status": ActionPlan.query.get(plan.id).effective_status},
                                        status=409)
        return jsonify({"plan_id": str(plan.id), "status": "cancelled"}), 200


class RHChatUpload(RHPlanBase):
    """POST /chat/uploads: keep a file sent in the chat for a later attach_file step (US9)."""

    def _process(self):
        from indico_assistant.services.actions.uploads import UploadRefused, store

        if "attach_file" not in enabled_actions(self.plugin.settings.get_all()):
            # (otherwise any user could fill Indico's storage with files nothing will ever attach)
            return self._error_response("ACTIONS_DISABLED", "Attaching files from the chat is not enabled",
                                        status=403)
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return self._validation_error("A file is required", field="file")
        try:
            file = store(self.user, upload.stream, upload.filename, request.form.get("session_id"))
        except UploadRefused as exc:
            status = {"FILE_TOO_LARGE": 413, "UNSUPPORTED_FILE_TYPE": 415}.get(exc.code, 422)
            return self._error_response(exc.code, str(exc), status=status)
        return jsonify({"uuid": file.uuid, "filename": file.filename, "size": file.size,
                        "content_type": file.content_type}), 201
