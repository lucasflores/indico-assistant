"""Which actions may be planned, and the shape rules every plan must pass before it is shown (FR-005, FR-012, FR-021)."""

import pytest

from indico_assistant.default_settings import WRITE_ACTIONS
from indico_assistant.services import actions
from indico_assistant.services.actions import enabled_actions, validate_plan
from indico_assistant.services.actions.base import Action, ActionArgs


class _Args(ActionArgs):
    event_id: int | None = None


class Local(Action):
    name = 'create_event'
    Args = _Args


class Remote(Action):
    name = 'add_teams_room'
    Args = _Args
    external = True


@pytest.fixture(autouse=True)
def catalogue(monkeypatch):
    monkeypatch.setattr(actions, 'ACTIONS', {'create_event': Local(), 'add_teams_room': Remote()})


def settings(**kw):
    return {'actions_enabled': True, 'actions_allowed': list(WRITE_ACTIONS), **kw}


def step(n, action='create_event', refs=None):
    return {'n': n, 'action': action, 'args': {}, 'refs': refs or {}}


def test_nothing_is_enabled_until_the_admin_switch_is_on():
    assert enabled_actions(settings(actions_enabled=False)) == frozenset()
    assert enabled_actions(settings(actions_allowed=['create_event'])) == {'create_event'}


def test_a_valid_plan():
    plan = [step(1), step(2, 'add_teams_room', {'event_id': '$1'})]
    assert validate_plan(plan, enabled_actions(settings())) == []


@pytest.mark.parametrize(('plan', 'error'), [
    ([step(1, 'drop_database')], 'unknown action'),
    ([step(1, 'add_teams_room'), step(2)], 'must come last'),
    ([step(1, refs={'event_id': '$2'}), step(2)], 'earlier step'),
    ([step(1, refs={'event_id': '$1'})], 'earlier step'),
    ([step(n) for n in range(1, 27)], 'at most 25'),
])
def test_invalid_plans(plan, error):
    assert any(error in e for e in validate_plan(plan, enabled_actions(settings())))


def test_disabled_actions_are_never_planned():
    errors = validate_plan([step(1), step(2, 'add_teams_room')], enabled_actions(settings(actions_allowed=['create_event'])))
    assert errors == ['Step 2: add_teams_room is not available']
