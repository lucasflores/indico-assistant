"""The analytics API and pages (spec 024, T024/T029/T037, SC-008): admin-only, the trace, the export."""

import json
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from flask import request, session
from werkzeug.exceptions import Forbidden, NotFound, Unauthorized

from indico.core.db import db

import indico_assistant.controllers.analytics as analytics
from indico_assistant.models import ChatMessage, ChatSession, FeedbackEntry, IssueReport, Turn, TurnStep, TurnText
from indico_assistant.services.analytics import stats
from indico_assistant.views import WPReportsAdmin

API = (analytics.RHAnalyticsStats, analytics.RHAnalyticsTurns, analytics.RHAnalyticsTurn, analytics.RHAnalyticsExport)


PATHS = {'assistant.analytics_stats': '/api/assistant/admin/analytics',
         'assistant.analytics_turns': '/api/assistant/admin/turns',
         'assistant.analytics_export': '/api/assistant/admin/turns/export.{fmt}',
         'assistant.analytics_turn': '/api/assistant/admin/turns/{turn_id}',
         'assistant.admin_analytics': '/admin/assistant-analytics/',
         'assistant.admin_analytics_turn': '/admin/assistant-analytics/turns/{turn_id}/'}


@pytest.fixture(autouse=True)
def no_limits(monkeypatch):
    # (the plugin's blueprint isn't registered in the test app: its URLs, as routed in blueprint.py)
    monkeypatch.setattr(analytics, 'url_for_plugin', lambda endpoint, **kw: PATHS[endpoint].format(**kw))
    limiter = MagicMock()
    limiter.check_rate.return_value = MagicMock(allowed=True)
    monkeypatch.setattr('indico_assistant.controllers.base.get_rate_limiter', lambda: limiter)
    monkeypatch.setattr(stats, '_cache', MagicMock(get=lambda key: None))


@pytest.fixture
def people(create_user):
    return {'admin': create_user(90, admin=True), 'user': create_user(91)}


def run(app, rh_class, viewer, query=None, **view_args):
    with app.test_request_context(query_string=query):
        request.view_args = view_args
        if viewer is not None:
            session.set_session_user(viewer)
        rh = rh_class()
        rh._process_args()
        rh._check_access()
        return rh._process()


def body(response):
    return json.loads(response.get_data())


@pytest.fixture
def turns(people):
    """A kept turn (with its chat, a step and its text) and a private one (GitHub), both rated down."""
    user = people['user']
    chat = ChatSession(user_id=user.id)
    db.session.add(chat)
    db.session.flush()
    rows = {}
    for name, private in (('kept', False), ('private', True)):
        question = ChatMessage(session_id=chat.id, role='user', content=f'{name} question')
        answer = ChatMessage(session_id=chat.id, role='assistant', content=f'{name} answer')
        db.session.add_all([question, answer])
        db.session.flush()
        now = datetime.now(UTC)
        turn = Turn(job_id=uuid4().hex, session_id=chat.id, message_id=question.id, answer_id=answer.id,
                    user_id=user.id, is_admin=False, private=private, route='connector' if private else 'data',
                    outcome='answered', rating=-1, queued_at=now, started_at=now, finished_at=now)
        db.session.add(turn)
        db.session.flush()
        db.session.add(TurnStep(turn_id=turn.id, seq=1, kind='llm', stage='QueryClassification'))
        db.session.add(FeedbackEntry(message_id=answer.id, user_id=user.id, feedback_type='comment', value='wrong'))
        if not private:
            db.session.add(TurnText(turn_id=turn.id, seq=1, kind='prompt', text='the prompt'))
        rows[name] = turn
    db.session.flush()
    return rows


@pytest.mark.parametrize('rh_class', [*API, analytics.RHAnalyticsPage, analytics.RHAnalyticsTurnPage])
def test_only_admins_get_in(app, db, people, rh_class):
    with pytest.raises(Forbidden):
        run(app, rh_class, people['user'], turn_id=1, fmt='csv')
    if rh_class in API:
        with pytest.raises(Unauthorized):
            run(app, rh_class, None, turn_id=1, fmt='csv')
        assert rh_class.RATE_LIMIT == 'read'


def test_the_stats(app, db, people, turns):
    got = body(run(app, analytics.RHAnalyticsStats, people['admin'], query={'range': '7d'}))
    assert got['tiles']['turns'] == 2 and got['params']['route'] is None
    got = body(run(app, analytics.RHAnalyticsStats, people['admin'], query={'range': '7d', 'route': 'data'}))
    assert got['tiles']['turns'] == 1
    with pytest.raises(Exception, match='Bad range'):
        run(app, analytics.RHAnalyticsStats, people['admin'], query={'range': 'forever'})


def test_the_turn_list_pages_newest_first(app, db, people, turns, monkeypatch):
    monkeypatch.setattr(analytics.turns, 'PAGE', 1)
    first = body(run(app, analytics.RHAnalyticsTurns, people['admin'], query={'range': '7d'}))
    assert [t['id'] for t in first['turns']] == [turns['private'].id] and first['next_before'] == turns['private'].id
    second = body(run(app, analytics.RHAnalyticsTurns, people['admin'],
                      query={'range': '7d', 'before': first['next_before']}))
    assert [t['id'] for t in second['turns']] == [turns['kept'].id] and second['next_before'] is None


def test_a_kept_trace_shows_the_chat_and_a_private_one_shows_nothing(app, db, people, turns):
    kept = body(run(app, analytics.RHAnalyticsTurn, people['admin'], turn_id=turns['kept'].id))
    assert (kept['text'], kept['question'], kept['answer'], kept['comment']) == (
        'kept', 'kept question', 'kept answer', 'wrong')
    assert kept['steps'][0]['texts'] == {'prompt': {'text': 'the prompt', 'cut': False}}
    private = body(run(app, analytics.RHAnalyticsTurn, people['admin'], turn_id=turns['private'].id))
    assert (private['text'], private['question'], private['answer']) == ('private', None, None)
    assert private['steps'][0]['texts'] == {}
    assert 'private question' not in json.dumps(private) and 'private answer' not in json.dumps(private)


def test_past_its_retention_a_trace_keeps_its_steps_and_no_text(app, db, people, turns):
    TurnText.query.filter_by(turn_id=turns['kept'].id).delete()
    got = body(run(app, analytics.RHAnalyticsTurn, people['admin'], turn_id=turns['kept'].id))
    assert (got['text'], got['question'], got['answer']) == ('none', None, None) and len(got['steps']) == 1


def test_a_turn_is_found_from_its_answer_and_from_a_report(app, db, people, turns):
    answer_id = turns['kept'].answer_id
    got = body(run(app, analytics.RHAnalyticsTurn, people['admin'], answer_id=answer_id))
    assert got['turn']['id'] == turns['kept'].id
    with pytest.raises(NotFound):
        run(app, analytics.RHAnalyticsTurn, people['admin'], turn_id=999999)
    report = IssueReport(user_id=people['user'].id, form_key=uuid4(), category='wrong_answer', text='x',
                         copy={'reported_answer_id': str(answer_id)})
    db.session.add(report)
    db.session.flush()
    got = body(run(app, analytics.RHAnalyticsTurn, people['admin'], turn_id=turns['kept'].id))
    assert [r['id'] for r in got['reports']] == [report.id]
    with app.test_request_context():
        assert analytics.answer_trace_url(answer_id).endswith(f'/{turns["kept"].id}/')


def test_the_export_logs_and_never_shows_a_private_turns_words(app, db, people, turns, caplog):
    with caplog.at_level(logging.INFO, logger=analytics.logger.name):
        got = body(run(app, analytics.RHAnalyticsExport, people['admin'], query={'range': '7d', 'text': '1'},
                       fmt='json'))
    rows = {row['id']: row for row in got['turns']}
    assert rows[turns['kept'].id]['question'] == 'kept question' and rows[turns['kept'].id]['answer'] == 'kept answer'
    assert rows[turns['private'].id]['question'] is None and rows[turns['private'].id]['answer'] is None
    assert f'user={people["admin"].id}' in caplog.text and 'text=True' in caplog.text
    csv_response = run(app, analytics.RHAnalyticsExport, people['admin'], query={'range': '7d'}, fmt='csv')
    assert csv_response.mimetype == 'text/csv' and csv_response.get_data(as_text=True).startswith('id,')


def test_the_pages_render_for_admins(app, db, people, monkeypatch):
    seen = {}
    monkeypatch.setattr(WPReportsAdmin, 'render_template',
                        staticmethod(lambda template, *args, **context: seen.update(template=template, **context)))
    run(app, analytics.RHAnalyticsPage, people['admin'])
    assert seen['template'] == 'admin_analytics.html' and seen['stats_url'].endswith('/admin/analytics')
    assert seen['asset']('charts.js').startswith('/api/assistant/admin/analytics/assets/charts.js?v=')
    run(app, analytics.RHAnalyticsTurnPage, people['admin'], turn_id=5)
    assert seen['template'] == 'admin_turn.html' and seen['trace_url'].endswith('/admin/turns/5')


def test_the_admin_menu_has_the_analytics(app, db, people):
    with app.test_request_context():
        session.set_session_user(people['admin'])
        assert analytics.admin_menu_item().title == 'Assistant analytics'
        session.set_session_user(people['user'])
        assert analytics.admin_menu_item() is None
