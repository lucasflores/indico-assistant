"""Issue reports: the JSON API (spec 021, contracts/api.md).

Feature: 021-issue-reports

Someone else's report, and one that does not exist, get the same 404, so the API never says which ids exist
(FR-014). The profile and admin pages (``report_pages.py``) call the same ``services.reports``.
"""

from __future__ import annotations

from flask import jsonify, request
from indico.core.db import db

from indico_assistant.controllers.base import RHSessionCSRFBase
from indico_assistant.models import IssueReport
from indico_assistant.services import reports


class RHReportsAPI(RHSessionCSRFBase):
    """Base of the report endpoints: CSRF when the Indico session is used (R10)."""

    def _refused(self, error):
        """A ReportError as the API answers it (a 429 is raised, with its Retry-After)."""
        if error.status == 429:
            raise self._rate_limit_error(error.retry_after) from None
        return self._error_response(error.code, error.message, error.details, status=error.status)


class RHReportCreate(RHReportsAPI):
    """POST /reports: send a report (spec 021 US1). The limit counts only a report that is stored (R8)."""

    def _process(self):
        try:
            report, created = reports.create_report(self.user, request.get_json(silent=True))
        except reports.ReportError as error:
            return self._refused(error)
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


class RHAdminReportsAPI(RHReportsAPI):
    """Triage (US3): Indico admins only (FR-015)."""

    ADMIN_ONLY = True
    RATE_LIMIT = "read"


class RHAdminReportList(RHAdminReportsAPI):
    """GET /admin/reports?status=&category=&page=: every report, newest first, 50 a page."""

    def _process(self):
        try:
            page = int(request.args.get('page') or 1)
            rows, page, pages = reports.admin_list(request.args.get('status'), request.args.get('category'), page)
        except ValueError:
            return self._validation_error('page must be a number', 'page')
        except reports.ReportError as error:
            return self._refused(error)
        known = reports.people(rows)
        return jsonify({'reports': [reports.admin_summary(r, known) for r in rows], 'page': page, 'pages': pages,
                        'open': reports.open_count()}), 200


class RHAdminReportDetail(RHAdminReportsAPI):
    """GET /admin/reports/<id>: the report with its whole copy, evidence included (FR-016)."""

    def _process(self):
        report = db.session.get(IssueReport, request.view_args['report_id'])
        if report is None:
            return self._not_found_error("Report")
        return jsonify(reports.admin_detail(report)), 200


class RHAdminReportUpdate(RHAdminReportsAPI):
    """PATCH /admin/reports/<id> {status, note, seen}: 409 STALE when the report changed since ``seen`` (R11)."""

    def _process(self):
        data = request.get_json(silent=True)
        data = data if isinstance(data, dict) else {}
        try:
            report = reports.admin_update(self.user, request.view_args['report_id'], data.get('status'),
                                          data.get('note'), data.get('seen'))
        except reports.ReportError as error:
            return self._refused(error)
        return jsonify(reports.admin_detail(report)), 200
