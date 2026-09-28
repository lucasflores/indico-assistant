"""Shared setup for chat-action tests: Indico's own page checks to compare against, and Teams in fake mode."""

import pytest
from werkzeug.exceptions import HTTPException

from indico.core.plugins import plugin_engine

from indico_assistant.services.actions.context import acting_as


@pytest.fixture
def page_allows(app):
    """Whether an Indico page (RH class) lets ``user`` in: its own _check_access, in a POST request as that user.

    ``checks`` are extra conditions a page applies in _process (e.g. the VC plugin's own ACL).
    """
    def _allows(rh_cls, user, *checks, **attrs):
        with app.test_request_context(method='POST'), acting_as(user):
            rh = rh_cls.__new__(rh_cls)
            rh.__dict__.update(attrs)
            try:
                rh._check_access()
            except HTTPException:
                return False
            return all(check() for check in checks)
    return _allows


@pytest.fixture
def action_allows(app):
    """Whether our action's check lets ``user`` do it, run as the planner and executor run it."""
    def _allows(action, user, **args):
        with acting_as(user):
            return action.check(user, action.Args.model_validate(args)) is None
    return _allows


@pytest.fixture
def people(create_user, dummy_event):
    admin = create_user(10, first_name='Ada', last_name='Admin', admin=True, email='ada@aithoth.com')
    manager = create_user(11, first_name='Lucas', last_name='Flores', email='lucas@aithoth.com')
    contributions_manager = create_user(12, first_name='Carla', last_name='Contribs', email='carla@aithoth.com')
    submitter = create_user(13, first_name='Sam', last_name='Submitter', email='sam@aithoth.com')
    stranger = create_user(14, first_name='Stan', last_name='Ger', email='stan@example.com')
    makoto = create_user(15, first_name='Makoto', last_name='Tanaka', email='makoto@aithoth.com')
    dummy_event.update_principal(manager, full_access=True)
    dummy_event.update_principal(contributions_manager, permissions={'contributions'})
    dummy_event.update_principal(submitter, permissions={'submit'})
    return {'admin': admin, 'manager': manager, 'contributions_manager': contributions_manager,
            'submitter': submitter, 'stranger': stranger, 'makoto': makoto}


@pytest.fixture
def teams(app, db, monkeypatch):
    """The vc_teams plugin (loaded for these tests, see tests/conftest.py) with its in-memory fake Graph;
    every user has a tenant account unless removed with ``fake.add_missing_user``."""
    from indico_vc_teams import graph
    from indico_vc_teams.fake_graph import FakeGraph

    plugin = plugin_engine.get_plugin('vc_teams')
    if plugin is None:
        pytest.skip('indico-plugin-vc-teams is not installed')
    plugin.settings.set_multi({'tenant_id': 'tenant', 'client_id': 'client', 'client_secret': 'secret',
                               'service_account': 'indico-bot@aithoth.com', 'email_domains': ['aithoth.com']})
    fake = FakeGraph()
    monkeypatch.setattr(graph, 'get_client', lambda: fake)
    return plugin, fake
