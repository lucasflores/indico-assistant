"""The report pages (spec 021): the user's "Assistant reports" in their profile (US2), and the admins' triage (US3).

Feature: 021-issue-reports

Indico RHs, so Indico checks who may see a profile (``RHUserBase``) and the CSRF token of every form POST (FR-022).
They go through ``services.reports``, as the JSON API does.
"""

from __future__ import annotations

from datetime import datetime

from flask import flash, redirect, request, session
from indico.core.db import db
from indico.core.plugins import url_for_plugin
from indico.modules.admin import RHAdminBase
from indico.modules.users.controllers import RHUserBase
from indico.util.date_time import format_datetime
from indico.web.menu import SideMenuItem
from werkzeug.exceptions import Forbidden, NotFound

from indico_assistant.models import IssueReport
from indico_assistant.models.report import CATEGORIES, LABELS, STATUSES
from indico_assistant.services import reports
from indico_assistant.views import WPReports, WPReportsAdmin

MENU_ITEM = 'assistant_reports'


def _profile_url(endpoint: str, user, **values) -> str:
    """A profile page's URL; someone else's profile (an admin looking) carries its user id, as Indico's do."""
    if user != session.user:
        values['user_id'] = user.id
    return url_for_plugin(endpoint, **values)


def message_time(iso: str) -> str:
    """A copied message's time (stored as ISO text), as Indico shows times to this viewer."""
    try:
        return format_datetime(datetime.fromisoformat(iso), 'short')
    except (TypeError, ValueError):
        return ''


def profile_menu_item(user) -> SideMenuItem | None:
    """The profile menu's "Assistant reports", once ``user`` has sent a report (FR-012)."""
    if user.can_be_modified(session.user) and reports.has_reports(user):
        return SideMenuItem(MENU_ITEM, 'Assistant reports', _profile_url('assistant.user_reports', user), 20)
    return None


class RHUserReports(RHUserBase):
    """The profile's list of the user's reports."""

    def _process(self):
        return WPReports.render_template(
            'reports.html', MENU_ITEM, user=self.user, reports=reports.own_reports(self.user), labels=LABELS,
            report_url=lambda report: _profile_url('assistant.user_report', self.user, report_id=report.id))


class RHUserReportBase(RHUserBase):
    def _check_access(self):
        # logged in, and allowed this profile, before the report is looked up: looked up for nobody, it failed with
        # a 500 for an existing id and a 404 for a missing one, which told anyone which ids exist (fresh review)
        RHUserBase._check_access(self)
        self.report = reports.own_report(self.user, request.view_args['report_id'])
        if self.report is None:
            raise NotFound


class RHUserReport(RHUserReportBase):
    """One report, as the user sees it: their text and the messages, not how answers were made (FR-013)."""

    def _process(self):
        return WPReports.render_template(
            'report.html', MENU_ITEM, user=self.user, report=self.report, copy=reports.user_view(self.report.copy),
            labels=LABELS, message_time=message_time, can_delete=self.user == session.user,
            delete_url=_profile_url('assistant.user_report_delete', self.user, report_id=self.report.id))


class RHUserReportDelete(RHUserReportBase):
    """POST: the reporter deletes the report (FR-013a). An admin looking at the profile cannot."""

    def _check_access(self):
        RHUserReportBase._check_access(self)
        if self.user != session.user:
            raise Forbidden

    def _process(self):
        reports.delete_own(self.user, self.report.id)
        flash('The report was deleted.', 'success')
        return redirect(_profile_url('assistant.user_reports', self.user))


# --- triage (US3) ------------------------------------------------------------------------------------------


def admin_menu_item() -> SideMenuItem | None:
    """The admin menu's "Assistant reports", with the number of open reports (FR-015)."""
    if session.user is None or not session.user.is_admin:
        return None
    return SideMenuItem(MENU_ITEM, 'Assistant reports', url_for_plugin('assistant.admin_reports'),
                        section='integration', badge=reports.open_count() or None)


class RHAdminReports(RHAdminBase):
    """Every report, newest first, a page at a time, filtered by status and category."""

    def _process(self):
        # an unknown value drops only itself (fresh review: it cleared both)
        filters = {'status': request.args.get('status') if request.args.get('status') in STATUSES else None,
                   'category': request.args.get('category') if request.args.get('category') in CATEGORIES else None}
        rows, page, pages = reports.admin_list(filters['status'], filters['category'],
                                               request.args.get('page', 1, type=int))
        return WPReportsAdmin.render_template(
            'admin_reports.html', MENU_ITEM, reports=rows, page=page, pages=pages, filters=filters, labels=LABELS,
            people=reports.people(rows),
            page_url=lambda n: url_for_plugin('assistant.admin_reports', page=n, **{k: v for k, v in filters.items() if v}),
            report_url=lambda report: url_for_plugin('assistant.admin_report', report_id=report.id))


class RHAdminReport(RHAdminBase):
    """One report with its whole copy and evidence (FR-016); POST saves the status and the note (FR-017)."""

    def _check_access(self):
        RHAdminBase._check_access(self)  # an admin before the lookup: a 404 would tell others which ids exist
        self.report = db.session.get(IssueReport, request.view_args['report_id'])
        if self.report is None:
            raise NotFound

    def _process(self):
        stale = False
        if request.method == 'POST':
            try:
                reports.admin_update(session.user, self.report.id, request.form.get('status'),
                                     request.form.get('note'), request.form.get('seen'))
            except reports.ReportError as error:
                if error.code != 'STALE':
                    flash(error.message, 'error')
                else:
                    stale = True  # shown with the current status and note, which the admin can save again
            else:
                flash('Saved.', 'success')
                return redirect(url_for_plugin('assistant.admin_report', report_id=self.report.id))
        report = self.report
        people = reports.people([report])
        return WPReportsAdmin.render_template(
            'admin_report.html', MENU_ITEM, report=report, copy=report.copy, labels=LABELS, stale=stale,
            reporter=people.get(report.user_id), updated_by=people.get(report.updated_by_id),
            seen=report.updated_at.isoformat() if report.updated_at else '', message_time=message_time,
            list_url=url_for_plugin('assistant.admin_reports'))
