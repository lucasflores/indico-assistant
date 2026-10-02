"""The analytics API and pages (spec 024): admin-only, rate-limited like the other reads (FR-019, constitution II).

The pages only draw what the JSON endpoints return. Every export is logged with who made it, when, its filters and
whether it had text (FR-021).
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from flask import Response, jsonify, request, session
from werkzeug.exceptions import BadRequest, NotFound

from indico.core.plugins import url_for_plugin
from indico.modules.admin import RHAdminBase
from indico.web.menu import SideMenuItem

from indico_assistant.controllers.base import RHChatBase
from indico_assistant.services.analytics import stats, turns

logger = logging.getLogger(__name__)

MENU_ITEM = 'assistant_analytics'
RANGES = {'24h': timedelta(hours=24), '7d': timedelta(days=7), '30d': timedelta(days=30), '90d': timedelta(days=90)}
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)  # "all time"


def params(args):
    """The range and filters of a request: ``range`` (24h, 7d, 30d, 90d, all) or ``since``/``until`` (ISO dates), and
    ``route``, ``model``, ``user``, ``event``, ``category``, ``admins=1``."""
    # to the minute: the cache key holds since/until, and requests in the same minute must share it (FR-020)
    now = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
    try:
        if args.get('since'):
            since = _instant(args['since'])
            until = _instant(args['until']) if args.get('until') else now
        else:
            name = args.get('range', '30d')
            since = EPOCH if name == 'all' else now - RANGES[name]
            until = now
        return stats.Params(since=since, until=until, tz=str(session.tzinfo or 'UTC'),
                            route=args.get('route') or None, model=args.get('model') or None,
                            user_id=args.get('user', type=int), event_id=args.get('event', type=int),
                            category_id=args.get('category', type=int), admins=args.get('admins') == '1')
    except (KeyError, ValueError) as exc:
        raise BadRequest(f'Bad range or filter: {exc}') from exc


def _instant(value):
    """A date or time from the page, in the admin's own timezone unless it says otherwise."""
    moment = datetime.fromisoformat(value)
    if moment.tzinfo:
        return moment
    tz = session.tzinfo
    return tz.localize(moment) if hasattr(tz, 'localize') else moment.replace(tzinfo=tz or UTC)


class RHAnalyticsBase(RHChatBase):
    ADMIN_ONLY = True
    RATE_LIMIT = 'read'


class RHAnalyticsStats(RHAnalyticsBase):
    """GET /admin/analytics: everything the page shows for a range and filters (cached 45 s)."""

    def _process(self):
        return jsonify(stats.collect(params(request.args)))


class RHAnalyticsTurns(RHAnalyticsBase):
    """GET /admin/turns: newest first, 50 a page (keyset: ``before``), filtered as the stats are, and by outcome."""

    def _process(self):
        rows, next_before = turns.turn_list(params(request.args), outcome=request.args.get('outcome') or None,
                                            before=request.args.get('before', type=int))
        return jsonify(stats._jsonable({'turns': rows, 'next_before': next_before}))


class RHAnalyticsTurn(RHAnalyticsBase):
    """GET /admin/turns/<id>: one turn's trace; GET /admin/turns/by-answer/<message id> finds it from a message."""

    def _process(self):
        turn_id = request.view_args.get('turn_id')
        if (answer_id := request.view_args.get('answer_id')) is not None:
            turn_id = turns.by_answer(answer_id)
        found = turns.trace(turn_id) if turn_id else None
        if found is None:
            raise NotFound('No such turn')
        for report in found['reports']:
            report['url'] = url_for_plugin('assistant.admin_report', report_id=report['id'])
        return jsonify(stats._jsonable(found))


class RHAnalyticsExport(RHAnalyticsBase):
    """GET /admin/turns/export.csv|json: the turns of the range and filters, ``text=1`` with their kept text."""

    def _process(self):
        fmt = request.view_args['fmt']
        q, with_text = params(request.args), request.args.get('text') == '1'
        rows = stats._jsonable(turns.export(q, with_text=with_text))
        logger.info('assistant analytics export: user=%s format=%s text=%s filters=%s rows=%d',
                    self.user.id, fmt, with_text, asdict(q), len(rows))
        if fmt == 'json':
            return jsonify({'turns': rows})
        return Response(turns.as_csv(rows), mimetype='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="assistant-turns.csv"'})


# --- pages ---------------------------------------------------------------------------------------------------

def admin_menu_item():
    if session.user is None or not session.user.is_admin:
        return None
    return SideMenuItem(MENU_ITEM, 'Assistant analytics', url_for_plugin('assistant.admin_analytics'),
                        section='integration')


class RHAnalyticsPage(RHAdminBase):
    def _process(self):
        from indico_assistant.blueprint import analytics_asset_url
        from indico_assistant.views import WPReportsAdmin
        return WPReportsAdmin.render_template(
            'admin_analytics.html', MENU_ITEM, asset=analytics_asset_url,
            stats_url=url_for_plugin('assistant.analytics_stats'),
            turns_url=url_for_plugin('assistant.analytics_turns'),
            export_url=url_for_plugin('assistant.analytics_export', fmt='csv'),
            turn_page=url_for_plugin('assistant.admin_analytics_turn', turn_id=0).rsplit('/0/', 1)[0] + '/')


class RHAnalyticsTurnPage(RHAdminBase):
    def _process(self):
        from indico_assistant.blueprint import analytics_asset_url
        from indico_assistant.views import WPReportsAdmin
        turn_id = request.view_args['turn_id']
        return WPReportsAdmin.render_template(
            'admin_turn.html', MENU_ITEM, asset=analytics_asset_url, turn_id=turn_id,
            trace_url=url_for_plugin('assistant.analytics_turn', turn_id=turn_id),
            back_url=url_for_plugin('assistant.admin_analytics'))


def answer_trace_url(answer_id):
    """For links from elsewhere (an issue report): the trace page of the turn that made this message, or None."""
    if not answer_id:
        return None
    try:
        turn_id = turns.by_answer(UUID(str(answer_id)))
    except ValueError:
        return None
    return url_for_plugin('assistant.admin_analytics_turn', turn_id=turn_id) if turn_id else None
