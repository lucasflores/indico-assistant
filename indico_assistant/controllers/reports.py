"""Issue reports: the JSON API (spec 021, contracts/api.md).

Feature: 021-issue-reports

Someone else's report, and one that does not exist, get the same 404, so the API never says which ids exist
(FR-014). The profile and admin pages (``report_pages.py``) call the same ``services.reports``.
"""

from __future__ import annotations

from flask import jsonify, request, session

from indico_assistant.controllers.base import RHChatBase
from indico_assistant.services import reports


class RHReportsAPI(RHChatBase):
    """Base of the report endpoints: Indico's CSRF check for requests made with the Indico session (R10).

    The assistant's API turns CSRF off because the chat panel's server calls it with a token
    (``X-Assistant-Auth``), which a malicious page cannot send. But it also accepts Indico's session cookie,
    which a same-site page could ride on: a report write carried by that cookie must bring the CSRF token.
    """

    CSRF_ENABLED = True

    def _check_csrf(self):
        if session.user is not None:  # the Indico cookie came with it (a token call carries none)
            super()._check_csrf()


class RHReportCreate(RHReportsAPI):
    """POST /reports: send a report (spec 021 US1). The limit counts only a report that is stored (R8)."""

    def _process(self):
        try:
            report, created = reports.create_report(self.user, request.get_json(silent=True))
        except reports.ReportError as error:
            if error.status == 429:
                raise self._rate_limit_error(error.retry_after) from None
            return self._error_response(error.code, error.message, error.details, status=error.status)
        return jsonify({'report_id': report.id, 'url': reports.report_url(report.id)}), 201 if created else 200


class RHReportList(RHReportsAPI):
    """GET /reports: the caller's own reports, newest first (US2)."""

    RATE_LIMIT = "read"

    def _process(self):
        return jsonify({'reports': [reports.summary(r) for r in reports.own_reports(self.user)]}), 200


class RHReportDetail(RHReportsAPI):
    """GET /reports/<id>: one of the caller's reports, as they see it (the evidence is the team's, FR-013)."""

    RATE_LIMIT = "read"

    def _process(self):
        report = reports.own_report(self.user, request.view_args['report_id'])
        if report is None:
            return self._not_found_error("Report")
        return jsonify(reports.user_detail(report)), 200


class RHReportDelete(RHReportsAPI):
    """DELETE /reports/<id>: the reporter deletes their report and its copy (FR-013a). Only the reporter."""

    RATE_LIMIT = "read"

    def _process(self):
        if not reports.delete_own(self.user, request.view_args['report_id']):
            return self._not_found_error("Report")
        return '', 204
