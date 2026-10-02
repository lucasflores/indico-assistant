"""The numbers of the analytics page (spec 024): one function, one SQL statement, per number (FR-015).

Every query over turns shares one scope: the range (``started_at``), the filters, and admins left out unless asked
for (``is_admin IS NOT TRUE``: a turn whose user is gone still counts). Days are the admin's own (``tz``). Rates are
hidden below their minimum count, and satisfaction comes with a 95% Wilson interval (FR-016). ``collect()`` builds
the page's payload, cached 45 s for each range and filter set in Indico's cache, so every web process shares it
(FR-020). Expected traffic is small for a long time: live SQL over indexed ranges, no rollups (plan, Technical
Context).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text as sql

from indico.core.cache import make_scoped_cache
from indico.core.db import db

MIN_RATINGS = 10
MIN_TURNS = 10
NO_END_AFTER = 160  # seconds: the task's hard limit plus 10 s
CACHE_SECONDS = 45
TOP = 10

_cache = make_scoped_cache('assistant-analytics')

T = 'plugin_assistant.turns'
S = 'plugin_assistant.turn_steps'
DAY = "(t.started_at AT TIME ZONE :tz)::date"
WAIT_MS = "extract(epoch FROM t.finished_at - coalesce(t.queued_at, t.started_at)) * 1000"  # what the user waits


@dataclass(frozen=True)
class Params:
    since: datetime
    until: datetime
    tz: str = 'UTC'
    route: str | None = None
    model: str | None = None
    user_id: int | None = None
    event_id: int | None = None
    category_id: int | None = None
    admins: bool = False

    def bind(self):
        return {'since': self.since, 'until': self.until, 'tz': self.tz, 'route': self.route, 'model': self.model,
                'user_id': self.user_id, 'event_id': self.event_id, 'category_id': self.category_id}


def scope(q, t='t'):
    """The WHERE every query over turns shares: the range and the filters."""
    parts = [f'{t}.started_at >= :since', f'{t}.started_at < :until']
    if not q.admins:
        parts.append(f'{t}.is_admin IS NOT TRUE')
    for column, value in (('route', q.route), ('user_id', q.user_id), ('event_id', q.event_id),
                          ('category_id', q.category_id)):
        if value is not None:
            parts.append(f'{t}.{column} = :{column}')
    if q.model:
        parts.append(f'EXISTS (SELECT 1 FROM {S} ms WHERE ms.turn_id = {t}.id AND ms.served_model = :model)')
    return ' AND '.join(parts)


def _rows(statement, q, **extra):
    return [dict(row._mapping) for row in db.session.execute(sql(statement), {**q.bind(), **extra})]


def _one(statement, q, **extra):
    return _rows(statement, q, **extra)[0]


def _p(column):
    return (f'percentile_cont(0.5) WITHIN GROUP (ORDER BY {column}) AS p50, '
            f'percentile_cont(0.9) WITHIN GROUP (ORDER BY {column}) AS p90, count({column}) AS n')


def wilson(k, n, minimum=MIN_RATINGS, z=1.96):
    """The share k/n with its 95% Wilson interval, or how many there are when too few to show (FR-016)."""
    if n < minimum:
        return {'n': n, 'min': minimum}
    p = k / n
    centre, spread = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return {'rate': p, 'lo': (centre - spread) / (1 + z * z / n), 'hi': (centre + spread) / (1 + z * z / n), 'n': n}


def rate(k, n, minimum=None):
    minimum = MIN_TURNS if minimum is None else minimum
    return {'rate': k / n, 'n': n} if n >= minimum else {'n': n, 'min': minimum}


# --- tiles and adoption (US1) ----------------------------------------------------------------------------------

def tiles(q):
    row = _one(f'''
        SELECT count(*) AS turns, count(DISTINCT t.user_id) AS users, sum(t.cost_usd) AS spend,
               coalesce(sum(t.unpriced_calls), 0) AS unpriced, coalesce(sum(t.llm_calls), 0) AS calls,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY {WAIT_MS}) AS p50_ms,
               count(*) FILTER (WHERE t.rating = 1) AS helpful, count(t.rating) AS rated
        FROM {T} t WHERE {scope(q)}''', q)
    return {**row, 'satisfaction': wilson(row['helpful'], row['rated']),
            'unpriced_share': row['unpriced'] / row['calls'] if row['calls'] else None,
            'cost_per_helpful': row['spend'] / row['helpful'] if row['spend'] is not None and row['helpful'] else None}


def turns_per_day_by_route(q):
    return _rows(f'''SELECT {DAY} AS day, coalesce(t.route, 'none') AS route, count(*) AS turns
                     FROM {T} t WHERE {scope(q)} GROUP BY 1, 2 ORDER BY 1, 2''', q)


def active_users(q):
    daily = _rows(f'''SELECT {DAY} AS day, count(DISTINCT t.user_id) AS users
                      FROM {T} t WHERE {scope(q)} GROUP BY 1 ORDER BY 1''', q)
    weekly = _rows(f'''SELECT date_trunc('week', t.started_at AT TIME ZONE :tz)::date AS week,
                              count(DISTINCT t.user_id) AS users
                       FROM {T} t WHERE {scope(q)} GROUP BY 1 ORDER BY 1''', q)
    return {'daily': daily, 'weekly': weekly}


def chats(q):
    return _one(f'''SELECT count(*) AS chats, percentile_cont(0.5) WITHIN GROUP (ORDER BY n) AS turns_per_chat_p50,
                           max(n) AS turns_per_chat_max
                    FROM (SELECT t.session_id, count(*) AS n FROM {T} t WHERE {scope(q)} GROUP BY 1) per_chat''', q)


def returning_users(q):
    """Users of the range who had asked before it."""
    return _one(f'''SELECT count(DISTINCT t.user_id) FILTER (WHERE EXISTS (
                               SELECT 1 FROM {T} p WHERE p.user_id = t.user_id AND p.started_at < :since)) AS returning,
                           count(DISTINCT t.user_id) AS users
                    FROM {T} t WHERE {scope(q)}''', q)


def top_events(q):
    return _rows(f'''SELECT t.event_id, e.title, coalesce(e.is_deleted, true) AS deleted, count(*) AS turns
                     FROM {T} t LEFT JOIN events.events e ON e.id = t.event_id
                     WHERE {scope(q)} AND t.event_id IS NOT NULL
                     GROUP BY 1, 2, 3 ORDER BY 4 DESC, 1 LIMIT {TOP}''', q)


def top_categories(q):
    return _rows(f'''SELECT t.category_id, c.title, count(*) AS turns
                     FROM {T} t LEFT JOIN categories.categories c ON c.id = t.category_id
                     WHERE {scope(q)} AND t.category_id IS NOT NULL
                     GROUP BY 1, 2 ORDER BY 3 DESC, 1 LIMIT {TOP}''', q)


# --- cost and tokens (US1) -------------------------------------------------------------------------------------

def spend_per_day(q):
    by_route = _rows(f'''SELECT {DAY} AS day, coalesce(t.route, 'none') AS key, sum(t.cost_usd) AS spend
                         FROM {T} t WHERE {scope(q)} GROUP BY 1, 2 ORDER BY 1, 2''', q)
    by_stage = _rows(f'''SELECT {DAY} AS day, s.stage AS key, sum(s.cost_usd) AS spend
                         FROM {T} t JOIN {S} s ON s.turn_id = t.id
                         WHERE {scope(q)} AND s.cost_usd IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2''', q)
    by_model = _rows(f'''SELECT {DAY} AS day, coalesce(s.served_model, s.requested_model) AS key,
                                sum(s.cost_usd) AS spend
                         FROM {T} t JOIN {S} s ON s.turn_id = t.id
                         WHERE {scope(q)} AND s.cost_usd IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2''', q)
    return {'route': by_route, 'stage': by_stage, 'model': by_model}


def cost_per_turn(q):
    return _rows(f'''SELECT coalesce(t.route, 'none') AS route, {_p('t.cost_usd')}
                     FROM {T} t WHERE {scope(q)} GROUP BY 1 ORDER BY 1''', q)


def tokens_by_stage(q):
    return _rows(f'''SELECT s.kind, s.stage, sum(s.prompt_tokens) AS prompt, sum(s.completion_tokens) AS completion,
                            count(*) AS calls
                     FROM {T} t JOIN {S} s ON s.turn_id = t.id
                     WHERE {scope(q)} AND s.kind IN ('llm', 'jev') GROUP BY 1, 2 ORDER BY 3 DESC NULLS LAST''', q)


def top_spenders(q):
    return _rows(f'''SELECT t.user_id, u.first_name || ' ' || u.last_name AS name, sum(t.cost_usd) AS spend,
                            count(*) AS turns
                     FROM {T} t LEFT JOIN users.users u ON u.id = t.user_id
                     WHERE {scope(q)} AND t.cost_usd IS NOT NULL
                     GROUP BY 1, 2 ORDER BY 3 DESC, 1 LIMIT {TOP}''', q)


def costliest_turns(q):
    return _rows(f'''SELECT t.id, t.route, t.cost_usd, t.llm_calls, t.started_at
                     FROM {T} t WHERE {scope(q)} AND t.cost_usd IS NOT NULL
                     ORDER BY t.cost_usd DESC, t.id DESC LIMIT {TOP}''', q)


# --- speed (US1) -----------------------------------------------------------------------------------------------

def latency_by_route(q):
    return _rows(f'''SELECT coalesce(t.route, 'none') AS route, {_p(WAIT_MS)}
                     FROM {T} t WHERE {scope(q)} AND t.finished_at IS NOT NULL GROUP BY 1 ORDER BY 1''', q)


def queue_wait(q):
    return _one(f'''SELECT {_p("extract(epoch FROM t.started_at - t.queued_at) * 1000")}
                    FROM {T} t WHERE {scope(q)} AND t.queued_at IS NOT NULL''', q)


def step_time(q):
    return _rows(f'''SELECT s.kind, s.stage, {_p('s.duration_ms')}
                     FROM {T} t JOIN {S} s ON s.turn_id = t.id WHERE {scope(q)} GROUP BY 1, 2 ORDER BY 1, 2''', q)


def model_time(q):
    return _rows(f'''SELECT coalesce(s.served_model, s.requested_model) AS model, {_p('s.duration_ms')}
                     FROM {T} t JOIN {S} s ON s.turn_id = t.id
                     WHERE {scope(q)} AND s.kind = 'llm' GROUP BY 1 ORDER BY 1''', q)


def kind_time(q, kind):
    """Query time (``sql``) or Jev's (``jev``)."""
    return _one(f'''SELECT {_p('s.duration_ms')} FROM {T} t JOIN {S} s ON s.turn_id = t.id
                    WHERE {scope(q)} AND s.kind = :kind''', q, kind=kind)


def time_limit_hits(q):
    return _one(f"SELECT count(*) AS hits FROM {T} t WHERE {scope(q)} AND t.outcome = 'timeout'", q)['hits']


# --- quality (US3) ---------------------------------------------------------------------------------------------

def satisfaction(q):
    by = {}
    for key, group in (('route', "coalesce(t.route, 'none')"), ('intent', 't.intent')):
        by[key] = _rows(f'''SELECT {group} AS key, count(*) FILTER (WHERE t.rating = 1) AS helpful,
                                   count(t.rating) AS rated
                            FROM {T} t WHERE {scope(q)} AND t.rating IS NOT NULL
                            {"AND t.intent IS NOT NULL" if key == "intent" else ""} GROUP BY 1 ORDER BY 1''', q)
    by['model'] = _rows(f'''SELECT m.model AS key, count(*) FILTER (WHERE t.rating = 1) AS helpful,
                                   count(t.rating) AS rated
                            FROM {T} t JOIN (SELECT DISTINCT turn_id, coalesce(served_model, requested_model) AS model
                                             FROM {S} WHERE kind = 'llm') m ON m.turn_id = t.id
                            WHERE {scope(q)} AND t.rating IS NOT NULL GROUP BY 1 ORDER BY 1''', q)
    return {key: [{**row, **wilson(row['helpful'], row['rated'])} for row in rows] for key, rows in by.items()}


def unrated_share(q):
    row = _one(f'''SELECT count(*) FILTER (WHERE t.rating IS NULL) AS unrated, count(*) AS answered
                   FROM {T} t WHERE {scope(q)} AND t.outcome = 'answered' ''', q)
    return rate(row['unrated'], row['answered'])


def thumbs_down_queue(q, limit=50):
    """The newest thumbs-down answers, with the user's comment while the chat exists, and a link to the trace."""
    return _rows(f'''SELECT t.id, t.route, t.started_at, t.cost_usd, t.private,
                            {WAIT_MS} AS wait_ms,
                            (SELECT coalesce(s.served_model, s.requested_model) FROM {S} s
                             WHERE s.turn_id = t.id AND s.kind = 'llm' ORDER BY s.seq DESC LIMIT 1) AS model,
                            (SELECT f.value FROM plugin_assistant.feedback_entries f
                             WHERE f.message_id = t.answer_id AND f.feedback_type = 'comment'
                             ORDER BY f.created_at DESC LIMIT 1) AS comment
                     FROM {T} t WHERE {scope(q)} AND t.rating = -1
                     ORDER BY t.started_at DESC, t.id DESC LIMIT :limit''', q, limit=limit)


def data_health(q):
    row = _one(f'''SELECT count(*) AS turns, count(*) FILTER (WHERE t.outcome = 'answered') AS answered,
                          count(*) FILTER (WHERE t.corrections > 0) AS corrected,
                          count(*) FILTER (WHERE EXISTS (SELECT 1 FROM {S} s WHERE s.turn_id = t.id AND s.kind = 'sql'
                                                         AND s.error_code = 'timeout')) AS timed_out,
                          count(*) FILTER (WHERE t.row_count = 0) AS empty,
                          count(*) FILTER (WHERE t.truncated) AS truncated
                   FROM {T} t WHERE {scope(q)} AND t.route = 'data' ''', q)
    return {key: rate(row[key], row['turns']) for key in ('answered', 'corrected', 'timed_out', 'empty', 'truncated')}


def outcomes(q):
    return _rows(f'''SELECT coalesce(t.route, 'none') AS route, coalesce(t.outcome, 'running') AS outcome,
                            count(*) AS turns
                     FROM {T} t WHERE {scope(q)} GROUP BY 1, 2 ORDER BY 1, 2''', q)


def reports_by_kind(q):
    """Issue reports made in the range, by kind; with the turn of the answer each one cites, when it has one."""
    return _rows('''SELECT r.category AS kind, count(*) AS reports, count(t.id) AS with_turn
                    FROM plugin_assistant.issue_reports r
                    LEFT JOIN plugin_assistant.turns t ON t.answer_id::text = r.copy->>'reported_answer_id'
                    WHERE r.created_at >= :since AND r.created_at < :until GROUP BY 1 ORDER BY 1''', q)


# --- routing and the agent's work (US4) ------------------------------------------------------------------------

def jev_confidence(q):
    return _rows(f'''SELECT least(width_bucket(t.jev_confidence, 0, 1, 10), 10) AS bucket, count(*) AS turns
                     FROM {T} t WHERE {scope(q)} AND t.jev_confidence IS NOT NULL GROUP BY 1 ORDER BY 1''', q)


def jev_skips(q):
    return _rows(f'''SELECT s.error_code AS reason, count(*) AS calls
                     FROM {T} t JOIN {S} s ON s.turn_id = t.id
                     WHERE {scope(q)} AND s.kind = 'jev' AND NOT s.ok GROUP BY 1 ORDER BY 2 DESC''', q)


def decided_by(q):
    return _rows(f'''SELECT coalesce(t.decided_by, 'none') AS decided_by, coalesce(t.fallback, '') AS fallback,
                            count(*) AS turns
                     FROM {T} t WHERE {scope(q)} GROUP BY 1, 2 ORDER BY 3 DESC''', q)


def negative_by_route(q):
    return _rows(f'''SELECT coalesce(t.route, 'none') AS route, count(*) FILTER (WHERE t.rating = -1) AS thumbs_down,
                            count(r.id) AS reports
                     FROM {T} t LEFT JOIN plugin_assistant.issue_reports r
                          ON r.copy->>'reported_answer_id' = t.answer_id::text
                     WHERE {scope(q)} GROUP BY 1 ORDER BY 1''', q)


def calls_per_turn(q):
    return _rows(f'''SELECT coalesce(t.route, 'none') AS route, avg(t.llm_calls) AS mean, {_p('t.llm_calls')},
                            max(t.llm_calls) AS max
                     FROM {T} t WHERE {scope(q)} AND t.finished_at IS NOT NULL GROUP BY 1 ORDER BY 1''', q)


def correction_loops(q):
    return _rows(f'''SELECT t.corrections, count(*) AS turns FROM {T} t
                     WHERE {scope(q)} AND t.route = 'data' AND t.corrections IS NOT NULL GROUP BY 1 ORDER BY 1''', q)


def tool_calls(q):
    return _rows(f'''SELECT s.name AS tool, count(*) AS calls, count(*) FILTER (WHERE NOT s.ok) AS failed,
                            percentile_cont(0.5) WITHIN GROUP (ORDER BY s.duration_ms) AS p50_ms
                     FROM {T} t JOIN {S} s ON s.turn_id = t.id
                     WHERE {scope(q)} AND s.kind = 'tool' GROUP BY 1 ORDER BY 2 DESC''', q)


def plan_funnel(q):
    """Plans made in the range: shown, confirmed, carried out, undone (read from action_plans)."""
    row = _one(f'''SELECT count(*) AS shown, count(p.confirmed_at) AS confirmed,
                          count(*) FILTER (WHERE p.status = 'done') AS done,
                          count(*) FILTER (WHERE EXISTS (SELECT 1 FROM plugin_assistant.action_plans u
                                                         WHERE u.undoes_id = p.id AND u.status = 'done')) AS undone,
                          {_p('extract(epoch FROM p.confirmed_at - p.created_at) * 1000')}
                   FROM plugin_assistant.action_plans p
                   WHERE p.created_at >= :since AND p.created_at < :until
                         {"AND p.user_id = :user_id" if q.user_id is not None else ""}''', q)
    return row


def plan_failures(q):
    return _rows(f'''SELECT coalesce(p.steps->0->>'action', 'none') AS action, p.status, count(*) AS plans
                     FROM plugin_assistant.action_plans p
                     WHERE p.created_at >= :since AND p.created_at < :until AND p.status IN ('failed', 'refused')
                           {"AND p.user_id = :user_id" if q.user_id is not None else ""}
                     GROUP BY 1, 2 ORDER BY 3 DESC''', q)


# --- errors (US5) ----------------------------------------------------------------------------------------------

def errors_by_type(q):
    """Per day: failed turns by code, provider rate limits and server errors (retried or not), query timeouts."""
    return _rows(f'''
        SELECT day, kind, count(*) AS errors FROM (
            SELECT {DAY} AS day, t.outcome || coalesce(':' || t.error_code, '') AS kind
            FROM {T} t WHERE {scope(q)} AND t.outcome IN ('failed', 'timeout', 'access_denied')
            UNION ALL
            SELECT {DAY}, CASE WHEN status = 429 THEN 'http:429' ELSE 'http:' || (status / 100) || 'xx' END
            FROM {T} t JOIN {S} s ON s.turn_id = t.id, unnest(s.http_errors) AS status WHERE {scope(q)}
            UNION ALL
            SELECT {DAY}, 'sql:timeout' FROM {T} t JOIN {S} s ON s.turn_id = t.id
            WHERE {scope(q)} AND s.kind = 'sql' AND s.error_code = 'timeout'
        ) errors GROUP BY 1, 2 ORDER BY 1, 2''', q)


def no_end_record(q):
    """Turns past the hard limit with no end: the worker died, or the end write failed (the log tells which)."""
    return _one(f'''SELECT count(*) AS turns FROM {T} t WHERE {scope(q)} AND t.finished_at IS NULL
                    AND t.started_at < now() - make_interval(secs => :after)''', q, after=NO_END_AFTER)['turns']


def facets(q):
    """The routes and models of the range, whatever the filters, for the page's selects."""
    unfiltered = Params(since=q.since, until=q.until, tz=q.tz, admins=q.admins)
    routes = _rows(f'''SELECT DISTINCT coalesce(t.route, 'none') AS route FROM {T} t
                       WHERE {scope(unfiltered)} ORDER BY 1''', unfiltered)
    models = _rows(f'''SELECT DISTINCT coalesce(s.served_model, s.requested_model) AS model
                       FROM {T} t JOIN {S} s ON s.turn_id = t.id
                       WHERE {scope(unfiltered)} AND s.kind = 'llm' AND coalesce(s.served_model, s.requested_model)
                             IS NOT NULL ORDER BY 1''', unfiltered)
    return {'routes': [r['route'] for r in routes], 'models': [m['model'] for m in models]}


# --- the payload -----------------------------------------------------------------------------------------------

def collect(q):
    """Everything the page shows for one range and filter set, cached 45 s (FR-020)."""
    key = hashlib.sha1(json.dumps(asdict(q), default=str, sort_keys=True).encode()).hexdigest()
    if (cached := _cache.get(key)) is not None:
        return cached
    payload = _jsonable({
        'params': asdict(q),
        'facets': facets(q),
        'tiles': tiles(q),
        'adoption': {'turns': turns_per_day_by_route(q), 'users': active_users(q), 'chats': chats(q),
                     'returning': returning_users(q), 'events': top_events(q), 'categories': top_categories(q)},
        'cost': {'spend': spend_per_day(q), 'per_turn': cost_per_turn(q), 'tokens': tokens_by_stage(q),
                 'spenders': top_spenders(q), 'costliest': costliest_turns(q)},
        'speed': {'latency': latency_by_route(q), 'queue': queue_wait(q), 'steps': step_time(q),
                  'models': model_time(q), 'sql': kind_time(q, 'sql'), 'jev': kind_time(q, 'jev'),
                  'time_limit_hits': time_limit_hits(q)},
        'quality': {'satisfaction': satisfaction(q), 'unrated': unrated_share(q), 'queue': thumbs_down_queue(q),
                    'data': data_health(q), 'outcomes': outcomes(q), 'reports': reports_by_kind(q)},
        'routing': {'jev_confidence': jev_confidence(q), 'jev_skips': jev_skips(q), 'decided_by': decided_by(q),
                    'negative': negative_by_route(q)},
        'depth': {'calls': calls_per_turn(q), 'corrections': correction_loops(q), 'tools': tool_calls(q)},
        'plans': {'funnel': plan_funnel(q), 'failures': plan_failures(q)},
        'errors': {'by_type': errors_by_type(q), 'no_end_record': no_end_record(q)},
    })
    _cache.set(key, payload, timeout=CACHE_SECONDS)
    return payload


def _jsonable(value):
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
