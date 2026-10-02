"""Every number of the analytics page against plain Python over a fixed seed (spec 024, T023/T033/T035/T037, SC-007)."""

from collections import Counter
from datetime import timedelta
from decimal import Decimal

import pytest

from indico_assistant.services.analytics import stats
from tests.integration.analytics.seed import BASE, pcont, seed, users_only


@pytest.fixture
def seeded(create_user, create_category, create_event):
    users = [create_user(60, admin=True), create_user(61), create_user(62)]
    categories = [create_category(70, title='Physics'), create_category(71, title='Biology')]
    events = [create_event(80, title='Budget review', category=categories[0]),
              create_event(81, title='Retreat', category=categories[1])]
    all_specs, rows = seed(users, events)
    return all_specs, rows, users, events


def params(**kwargs):
    return stats.Params(since=BASE, until=BASE + timedelta(days=30), tz='UTC', **kwargs)


def test_tiles(seeded):
    all_specs, rows, users, _ = seeded
    view = users_only(all_specs)
    got = stats.tiles(params())
    assert got['turns'] == len(view) and got['users'] == 2
    assert got['spend'] == sum(sum(st[3] for st in s.steps if st[3] is not None) for s in view)
    rated = [s for s in view if s.rating is not None]
    assert (got['helpful'], got['rated']) == (sum(1 for s in rated if s.rating == 1), len(rated))
    assert got['satisfaction']['n'] == len(rated) and 'rate' in got['satisfaction']
    done = [s.wait_ms for s in view if s.outcome is not None]
    assert got['p50_ms'] == pytest.approx(pcont(done, 0.5))
    # admins are left out unless asked for
    assert stats.tiles(params(admins=True))['turns'] == len(all_specs)


def test_turns_per_day_by_route_and_the_route_filter(seeded):
    all_specs = seeded[0]
    want = Counter((BASE.date() + timedelta(days=s.day), s.route) for s in users_only(all_specs))
    got = {(row['day'], row['route']): row['turns'] for row in stats.turns_per_day_by_route(params())}
    assert got == dict(want)
    only = stats.turns_per_day_by_route(params(route='data'))
    assert {row['route'] for row in only} == {'data'}
    assert stats.tiles(params(route='data'))['turns'] == sum(1 for s in users_only(all_specs) if s.route == 'data')


def test_a_range_covers_exactly_its_days(seeded):
    all_specs = seeded[0]
    week = stats.Params(since=BASE, until=BASE + timedelta(days=7), tz='UTC')
    assert stats.tiles(week)['turns'] == sum(1 for s in users_only(all_specs) if s.day < 7)


def test_cost_and_unpriced(seeded):
    all_specs = seeded[0]
    view = users_only(all_specs)
    calls = [st for s in view for st in s.steps if st[0] == 'llm']
    tiles = stats.tiles(params())
    assert tiles['unpriced_share'] == pytest.approx(sum(1 for st in calls if st[3] is None) / len(calls))
    per_route = {row['route']: row for row in stats.cost_per_turn(params())}
    for route in ('data', 'chat'):
        costs = [float(sum(st[3] for st in s.steps if st[3] is not None)) for s in view
                 if s.route == route and any(st[3] is not None for st in s.steps)]
        assert per_route[route]['p50'] == pytest.approx(pcont(costs, 0.5))
    spenders = stats.top_spenders(params())
    assert spenders[0]['spend'] >= spenders[-1]['spend']
    tokens = {row['stage']: row for row in stats.tokens_by_stage(params())}
    assert tokens['QueryClassification']['prompt'] == sum(st[4] for st in calls)


def test_speed(seeded):
    view = users_only(seeded[0])
    queue = stats.queue_wait(params())
    assert queue['p50'] == pytest.approx(pcont([s.queue_ms for s in view], 0.5), abs=1)
    sql = stats.kind_time(params(), 'sql')
    assert sql['n'] == sum(1 for s in view for st in s.steps if st[0] == 'sql')
    assert stats.time_limit_hits(params()) == sum(1 for s in view if s.outcome == 'timeout')


def test_satisfaction_needs_ten_ratings(seeded):
    view = users_only(seeded[0])
    by_route = {row['key']: row for row in stats.satisfaction(params())['route']}
    for route, row in by_route.items():
        rated = [s for s in view if s.route == route and s.rating is not None]
        assert row['rated'] == len(rated)
        assert ('rate' in row) == (len(rated) >= stats.MIN_RATINGS)  # (8 or fewer per route here: all hidden)
    assert stats.wilson(9, 9) == {'n': 9, 'min': 10}
    w = stats.wilson(8, 10)  # hand-computed: p=0.8, n=10
    assert (round(w['lo'], 4), round(w['hi'], 4)) == (0.4902, 0.9433)


def test_quality_queue_and_data_health(seeded, monkeypatch):
    view = users_only(seeded[0])
    queue = stats.thumbs_down_queue(params())
    assert len(queue) == sum(1 for s in view if s.rating == -1)
    assert [row['started_at'] for row in queue] == sorted((row['started_at'] for row in queue), reverse=True)
    data = [s for s in view if s.route == 'data']
    assert stats.data_health(params())['empty'] == {'n': len(data), 'min': stats.MIN_TURNS}  # (too few: hidden)
    monkeypatch.setattr(stats, 'MIN_TURNS', 1)
    health = stats.data_health(params())
    for key, count in (('empty', sum(1 for s in data if s.row_count == 0)),
                       ('truncated', sum(1 for s in data if s.truncated)),
                       ('corrected', sum(1 for s in data if s.corrections)),
                       ('timed_out', sum(1 for s in data for st in s.steps if st[8] == 'timeout'))):
        assert health[key] == {'rate': count / len(data), 'n': len(data)}, key


def test_routing_depth_and_tools(seeded):
    view = users_only(seeded[0])
    tools = stats.tool_calls(params())
    calls = [st for s in view for st in s.steps if st[0] == 'tool']
    assert calls and [(t['tool'], t['calls'], t['failed']) for t in tools] == [
        ('my_pull_requests', len(calls), sum(1 for st in calls if not st[7]))]
    per_route = {row['route']: row for row in stats.calls_per_turn(params())}
    assert per_route['data']['max'] == 1  # (one llm step each in the seed)


def test_errors_and_no_end_record(seeded):
    view = users_only(seeded[0])
    errors = Counter()
    for row in stats.errors_by_type(params()):
        errors[row['kind']] += row['errors']
    assert errors['http:429'] == sum(1 for s in view for st in s.steps if st[9] == [429])
    assert errors['sql:timeout'] == sum(1 for s in view for st in s.steps if st[0] == 'sql' and st[8] == 'timeout')
    assert errors['failed:QUERY_PROCESSING_ERROR'] == sum(1 for s in view if s.outcome == 'failed')
    assert stats.no_end_record(params()) == sum(1 for s in view if s.outcome is None)


def test_the_selects_offer_every_route_and_model_of_the_range(seeded):
    view = users_only(seeded[0])
    facets = stats.facets(params(route='data'))  # (a filter narrows the numbers, not the choices)
    assert facets['routes'] == sorted({s.route for s in view})
    assert facets['models'] == sorted({st[2] for s in view for st in s.steps if st[0] == 'llm'})


def test_the_payload_is_cached_45_seconds(seeded, monkeypatch):
    calls = []
    real = stats.tiles
    monkeypatch.setattr(stats, 'tiles', lambda q: calls.append(q) or real(q))
    first = stats.collect(params())
    assert stats.collect(params()) == first and len(calls) == 1
    stats.collect(params(route='data'))  # another filter set: its own entry
    assert len(calls) == 2
    assert isinstance(first['tiles']['spend'], float)  # (JSON-ready)
    assert Decimal(str(first['tiles']['spend'])) > 0
