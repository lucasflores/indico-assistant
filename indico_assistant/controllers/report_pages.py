"""The report pages (spec 021): the user's "Assistant reports" in their profile (US2).

Feature: 021-issue-reports

Indico RHs, so Indico checks who may see a profile (``RHUserBase``) and the CSRF token of every form POST (FR-022).
They go through ``services.reports``, as the JSON API does.
"""

from __future__ import annotations

from datetime import datetime

from flask import flash, redirect, request, session
from indico.core.plugins import url_for_plugin
from indico.modules.users.controllers import RHUserBase
from indico.util.date_time import format_datetime
from indico.web.menu import SideMenuItem
from werkzeug.exceptions import Forbidden, NotFound

from indico_assistant.models.report import LABELS
from indico_assistant.services import reports
from indico_assistant.views import WPReports

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
    def _process_args(self):
        RHUserBase._process_args(self)
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
