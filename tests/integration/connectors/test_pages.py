"""The "Connected accounts" page and GitHub's sign-in (spec 023, US1: T012-T014, T016).

The RHs run with Indico's own access checks (RHUserBase, RHProtected) in a request context, against the fake
GitHub; the template rendering is captured instead of drawn (the page itself is checked live, T040).
"""

from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet
from flask import request, session
from werkzeug.exceptions import Forbidden, NotFound

import indico_assistant.controllers.connections as pages
import indico_assistant.controllers.report_pages as report_pages
from indico_assistant.models import Connection
from indico_assistant.services.connectors import github, store
from indico_assistant.services.connectors.fake_github import USER, FakeGitHub
from indico_assistant.views import WPConnections

SETTINGS = {"github_enabled": True, "github_client_id": "Iv1.fake", "github_client_secret": "fake-secret",
            "github_app_url": "https://github.com/apps/indico-assistant", "github_timeout_seconds": 5}


@pytest.fixture
def users(create_user):
    return {'lucas': create_user(20, first_name='Lucas', admin=True), 'makoto': create_user(21, first_name='Makoto')}


@pytest.fixture
def fake(tmp_path, monkeypatch):
    fake = FakeGitHub(tmp_path / "fake.json")
    monkeypatch.setattr(github, "_transport", fake.transport)
    monkeypatch.setenv(store.KEY_ENV, Fernet.generate_key().decode())
    return fake


@pytest.fixture
def settings(monkeypatch):
    values = dict(SETTINGS)
    monkeypatch.setattr(pages, "_settings", lambda: values)
    return values


@pytest.fixture
def rendered(monkeypatch, settings, fake):
    seen = {}

    def render(template, *wp_args, **context):
        seen.update(template=template, wp_args=wp_args, **context)
        return 'page'

    def url(endpoint, **kw):
        return f'/{endpoint}/' + '&'.join(f'{k}={v}' for k, v in sorted(kw.items()))

    monkeypatch.setattr(WPConnections, 'render_template', staticmethod(render))
    for module in (pages, report_pages):
        monkeypatch.setattr(module, 'url_for_plugin', url)
    monkeypatch.setattr(pages, 'flash', MagicMock())
    return seen


def run(app, rh_class, viewer, method='GET', query=None, keep=None, **view_args):
    """Process ``rh_class`` as Indico would after routing: arguments, access, then the page. ``keep``: session data
    carried over from an earlier request (the sign-in's state)."""
    with app.test_request_context(method=method, query_string=query):
        request.view_args = view_args
        if viewer is not None:
            session.set_session_user(viewer)
        session.update({k: v for k, v in (keep or {}).items() if k == pages.OAUTH_KEY})  # (not who's logged in)
        rh = rh_class()
        rh._process_args()
        rh._check_access()
        response = rh._process()
        return response, dict(session)


def connect(app, user):
    """Connect and come back through the callback as GitHub would, the code and state in the query."""
    response, saved = run(app, pages.RHConnect, user, method='POST')
    query = {k: v[0] for k, v in parse_qs(urlsplit(response.location).query).items()}
    return run(app, pages.RHGitHubCallback, user, query={'code': 'fake-code', 'state': query['state']}, keep=saved)


# --- the page (T012) ---------------------------------------------------------------------------------------

def test_an_anonymous_visitor_is_sent_to_log_in(app, db, users, rendered):
    with pytest.raises(Exception) as raised:  # (Indico's login redirect, not a 404 or a 500)
        run(app, pages.RHConnections, None)
    assert raised.type.__name__ in ('Unauthorized', 'Forbidden') or 'login' in str(raised.value).lower()


def test_unconnected_the_page_offers_connect(app, db, users, rendered):
    run(app, pages.RHConnections, users['makoto'])
    assert rendered['template'] == 'connections.html' and rendered['wp_args'][-1] == 'assistant_connections'
    assert rendered['connection'] is None and rendered['own'] and rendered['connect_url']


def test_connected_the_page_shows_the_account_and_what_it_can_see(app, db, users, rendered):
    connect(app, users['makoto'])
    run(app, pages.RHConnections, users['makoto'])
    assert rendered['connection'].account_login == USER and rendered['disconnect_url']
    names = [r['full_name'] for r in rendered['repos']]
    assert 'thoth-labs/indico-assistant' in names and 'thoth-labs/secret-infra' not in names
    assert rendered['repo_count'] == len(names) and rendered['add_url'].endswith('/installations/new')


def test_a_github_error_while_listing_still_renders_the_page(app, db, users, rendered, fake):
    connect(app, users['makoto'])
    fake.fail_next("/user/installations", 502)
    run(app, pages.RHConnections, users['makoto'])
    assert rendered['repos'] is None and rendered['repos_failed'] and rendered['connection']


def test_an_admin_sees_another_users_connection_but_not_their_repositories(app, db, users, rendered, fake):
    connect(app, users['makoto'])
    before = len(fake.calls)
    run(app, pages.RHConnections, users['lucas'], user_id=users['makoto'].id)
    assert rendered['connection'].account_login == USER and not rendered['own'] and rendered['disconnect_url']
    assert rendered['repos'] is None and fake.calls[before:] == []  # (the admin never reads GitHub as the user)


def test_github_off_keeps_the_page_only_for_a_connection_to_remove(app, db, users, rendered, settings, fake):
    """(fresh-review) off, the user can still see and remove their own connection; nothing is read from GitHub."""
    connect(app, users['makoto'])
    settings['github_enabled'] = False
    before = len(fake.calls)
    run(app, pages.RHConnections, users['makoto'])
    assert rendered['connection'] and rendered['disconnect_url'] and not rendered['enabled'] and rendered['repos'] is None
    assert fake.calls[before:] == []
    with pytest.raises(NotFound):
        run(app, pages.RHConnect, users['makoto'], method='POST')  # (and can't connect again while it's off)
    run(app, pages.RHConnections, users['lucas'], user_id=users['makoto'].id)
    assert rendered['connection'] and rendered['disconnect_url']
    with pytest.raises(NotFound):
        run(app, pages.RHConnections, users['lucas'])  # (none of his own)


def test_someone_elses_page_is_refused_to_a_non_admin(app, db, users, rendered):
    with pytest.raises(Forbidden):
        run(app, pages.RHConnections, users['makoto'], user_id=users['lucas'].id)


# --- connecting (T013) -------------------------------------------------------------------------------------

def test_connect_is_a_post_with_csrf(monkeypatch):
    """(The test app doesn't load the plugin's blueprint: its rules are read as they are added.)"""
    from flask import Blueprint

    import indico_assistant.blueprint as blueprint

    rules = {}
    monkeypatch.setattr(Blueprint, 'add_url_rule', lambda self, rule, endpoint=None, view_func=None, **kw:
                        rules.setdefault(endpoint, []).append((rule, set(kw.get('methods') or ['GET']))))
    blueprint._register_routes()
    assert all(methods == {'POST'} for _, methods in rules['github_connect'] + rules['github_disconnect'])
    assert pages.RHConnect.CSRF_ENABLED and pages.RHDisconnect.CSRF_ENABLED
    assert rules['github_callback'] == [('!' + github.CALLBACK_PATH, {'GET'})]
    assert {rule for rule, _ in rules['user_connections']} == {'!/user/<int:user_id>/assistant-connections/',
                                                              '!/user/assistant-connections/'}


def test_connect_sends_the_user_to_github_with_state_and_pkce(app, db, users, rendered):
    response, saved = run(app, pages.RHConnect, users['makoto'], method='POST')
    url = urlsplit(response.location)
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert (url.netloc, url.path) == ('github.com', '/login/oauth/authorize')
    assert query['client_id'] == 'Iv1.fake' and query['code_challenge_method'] == 'S256'
    assert query['redirect_uri'] == github.callback_url() and len(query['code_challenge']) == 43
    kept = saved[pages.OAUTH_KEY]
    assert kept['state'] == query['state'] and kept['user_id'] == users['makoto'].id and kept['verifier']


def test_the_callback_stores_the_connection(app, db, users, rendered):
    response, saved = connect(app, users['makoto'])
    row = Connection.query.filter_by(user_id=users['makoto'].id).one()
    assert row.account_login == USER and response.location.startswith('/assistant.user_connections/')
    assert pages.OAUTH_KEY not in saved  # (one use)
    pages.flash.assert_called_with(f'GitHub is connected as @{USER}.', 'success')


@pytest.mark.parametrize('case', ['wrong state', 'no state', 'reused', 'another user', 'refused', 'not ascii'])
def test_a_callback_that_doesnt_check_out_stores_nothing(app, db, users, rendered, case):
    _, saved = run(app, pages.RHConnect, users['makoto'], method='POST')
    state = saved[pages.OAUTH_KEY]['state']
    query = {'code': 'fake-code', 'state': state}
    who = users['makoto']
    if case == 'wrong state':
        query['state'] = 'forged'
    elif case == 'no state':
        del query['state']
    elif case == 'reused':
        saved = {k: v for k, v in saved.items() if k != pages.OAUTH_KEY}
    elif case == 'another user':
        who = users['lucas']  # (Makoto's sign-in, finished in Lucas's session)
    elif case == 'refused':
        query = {'error': 'access_denied', 'state': state}
    elif case == 'not ascii':  # (fresh-review: compare_digest refused non-ASCII text with a TypeError, a 500)
        query['state'] = 'é' + state
    run(app, pages.RHGitHubCallback, who, query=query, keep=saved)
    assert Connection.query.count() == 0


def test_only_your_own_github_can_be_connected(app, db, users, rendered):
    with pytest.raises(Forbidden):
        run(app, pages.RHConnect, users['lucas'], method='POST', user_id=users['makoto'].id)


def test_fake_mode_comes_straight_back_to_the_callback(app, db, users, rendered, monkeypatch):
    monkeypatch.setattr(github, 'fake_enabled', lambda: True)
    response, _ = run(app, pages.RHConnect, users['makoto'], method='POST')
    assert response.location.startswith('/assistant.github_callback/') and 'code=fake' in response.location


# --- disconnecting (T014) ----------------------------------------------------------------------------------

def test_disconnect_your_own(app, db, users, rendered, fake):
    connect(app, users['makoto'])
    response, _ = run(app, pages.RHDisconnect, users['makoto'], method='POST')
    assert Connection.query.count() == 0 and response.location.startswith('/assistant.user_connections/')
    assert ('DELETE', '/applications/Iv1.fake/grant') in fake.calls


def test_an_admin_disconnects_another_user(app, db, users, rendered):
    connect(app, users['makoto'])
    response, _ = run(app, pages.RHDisconnect, users['lucas'], method='POST', user_id=users['makoto'].id)
    assert Connection.query.count() == 0 and f"user_id={users['makoto'].id}" in response.location


def test_a_non_admin_cant_disconnect_someone_else(app, db, users, rendered):
    connect(app, users['lucas'])
    with pytest.raises(Forbidden):
        run(app, pages.RHDisconnect, users['makoto'], method='POST', user_id=users['lucas'].id)
    assert Connection.query.count() == 1


# --- the menu (T016) ---------------------------------------------------------------------------------------

def test_the_menu_item(app, db, users, rendered, settings):
    def item(viewer, user):
        with app.test_request_context():
            session.set_session_user(viewer)
            return pages.profile_menu_item(user)

    assert item(users['makoto'], users['makoto']).title == 'Connected accounts'
    assert item(users['lucas'], users['makoto']) is None  # (no connection to look at)
    connect(app, users['makoto'])
    assert item(users['lucas'], users['makoto']) is not None
    settings['github_enabled'] = False
    assert item(users['makoto'], users['makoto']) is not None  # (fresh-review: theirs to remove)
    assert item(users['lucas'], users['makoto']) is not None  # (an admin can still remove it)
    assert item(users['lucas'], users['lucas']) is None  # (off, and nothing to remove)


# --- no token anywhere (SC-004, T037) ----------------------------------------------------------------------

def test_no_token_leaks_through_a_whole_connection(app, db, users, rendered, fake, settings, caplog, monkeypatch):
    """Connect, the page, the API, a refresh, an answer and a disconnect: every token GitHub issued is then looked
    for in the logs, the redirects, the page's data, the API's body, the model's prompts and the route record."""
    import logging
    from datetime import UTC, datetime
    from uuid import uuid4

    from indico_assistant.controllers import connections as api_module
    from indico_assistant.services.chat.service import _route_record
    from indico_assistant.services.turn import abilities, loop
    from indico_assistant.services.turn.answer import Outcome
    from indico_assistant.services.turn.tools import Ctx

    caplog.set_level(logging.DEBUG)
    issued, seen = set(), []

    def remember():
        issued.update(fake.state["tokens"], fake.state["refresh"])

    makoto = users['makoto']
    response, _ = run(app, pages.RHConnect, makoto, method='POST')
    seen.append(response.location)
    response, _ = connect(app, makoto)
    seen.append(response.location)
    remember()
    run(app, pages.RHConnections, makoto)
    seen.append(repr(rendered))

    request = MagicMock(view_args={})
    monkeypatch.setattr(api_module, 'request', request)
    rh = api_module.RHConnectionsAPI.__new__(api_module.RHConnectionsAPI)
    rh._user = makoto
    with app.test_request_context():
        seen.append(rh._process()[0].get_data(as_text=True))

    Connection.query.filter_by(user_id=makoto.id).one().access_expires_at = datetime.now(UTC)  # (refreshed next)
    prompts = []

    class Recording:
        def generate(self, prompt, response_model, **kwargs):
            prompts.append((prompt, kwargs))
            step = (response_model(call={"tool": "github_my_pull_requests"}) if len(prompts) == 1
                    else response_model(**({"reply": "Done."} if "reply" in response_model.model_fields
                                           else {"answer": {"reply": "Done."}})))
            return MagicMock(success=True, result=step, calls=[])

    ctx = Ctx(user=makoto, session_id=uuid4(), message_id=None, page_event_id=None, history=[], settings=settings,
              llm=Recording(), base_url="http://indico.test")
    result = loop.run(ctx, "which of my PRs are open?", abilities.registry(ctx, nl2sql=False, github=True),
                      system_prompt="RULES")
    ctx.github.close()
    remember()
    record = _route_record("agent", Outcome(result.text, {}, "agent", result=result, tools=result.tools, private=True))
    seen += [repr(prompts), repr(record), result.text]
    with app.test_request_context():
        session.set_session_user(makoto)
        store.disconnect(makoto.id, github.app_for(settings))
    seen.append(caplog.text)

    assert len(issued) >= 4  # (the first pair, then the refreshed pair)
    for token in issued:
        assert all(token not in text for text in seen), "a token leaked"


def test_the_callback_without_the_key_says_so_instead_of_failing(app, db, users, rendered, monkeypatch):
    """(third review) the key missing from the web server: a message, not a 500."""
    _, saved = run(app, pages.RHConnect, users['makoto'], method='POST')
    monkeypatch.delenv(store.KEY_ENV)
    run(app, pages.RHGitHubCallback, users['makoto'], query={'code': 'fake-code',
                                                           'state': saved[pages.OAUTH_KEY]['state']}, keep=saved)
    assert Connection.query.count() == 0 and pages.flash.call_args.args[1] == 'error'
