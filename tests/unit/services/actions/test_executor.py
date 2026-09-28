"""Carrying out a confirmed plan: all or nothing (research R2, SC-006)."""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from flask import g, session

from indico_assistant.models import ActionPlan, ChatMessage, ChatSession
from indico_assistant.services import actions
from indico_assistant.services.actions import executor
from indico_assistant.services.actions.base import Action, ActionArgs, on_rollback


class NoteArgs(ActionArgs):
    text: str


class WriteNote(Action):
    """Writes a row, so rollback is visible."""
    name = 'test_note'
    Args = NoteArgs

    def check(self, user, args):
        return None

    def describe(self, args):
        return f'Note {args.text}', []

    def execute(self, user, args):
        assert session.user == user  # executed as the user
        message = ChatMessage(session_id=g.test_chat_id, role='user', content=args.text)
        from indico.core.db import db
        db.session.add(message)
        db.session.flush()
        g.email_queue = [*g.get('email_queue', []), 'mail']  # as Indico's notifications do
        return {'created': {'message_id': str(message.id)}}


class EventArgs(ActionArgs):
    event_id: int


class MoveEvent(Action):
    """Changes event times: raises unless the executor tracks time changes."""
    name = 'test_move'
    Args = EventArgs

    def check(self, user, args):
        return None

    def describe(self, args):
        return 'Move', []

    def execute(self, user, args):
        from indico.modules.events import Event
        event = Event.get(args.event_id)
        event.end_dt += timedelta(minutes=10)
        return {'created': None}


class External(Action):
    name = 'test_external'
    Args = EventArgs
    external = True
    undone = []

    def check(self, user, args):
        return None

    def describe(self, args):
        return 'External', []

    def execute(self, user, args):
        on_rollback(lambda: External.undone.append(args.event_id))
        return {'created': {'remote_id': 'r1'}}


class Boom(Action):
    name = 'test_boom'
    Args = EventArgs

    def check(self, user, args):
        return None

    def describe(self, args):
        return 'Boom', []

    def execute(self, user, args):
        raise RuntimeError('boom')


class Forbidden(Boom):
    name = 'test_forbidden'

    def check(self, user, args):
        return 'You cannot manage this event'


@pytest.fixture(autouse=True)
def fake_actions(monkeypatch):
    for action in (WriteNote(), MoveEvent(), External(), Boom(), Forbidden()):
        monkeypatch.setitem(actions.ACTIONS, action.name, action)
    External.undone = []


@pytest.fixture
def chat(db, dummy_user):
    chat = ChatSession(user_id=dummy_user.id)
    db.session.add(chat)
    db.session.flush()
    g.test_chat_id = chat.id
    return chat


@pytest.fixture
def run(chat, dummy_user, dummy_event, monkeypatch):
    discard = MagicMock()
    monkeypatch.setattr(executor, '_discard_vc_pending', discard)

    def _run(*names):
        steps = [{'n': i, 'action': name,
                  'args': {'text': f'n{i}'} if name == 'test_note' else {'event_id': dummy_event.id}}
                 for i, name in enumerate(names, 1)]
        plan, token = executor.create_plan(dummy_user, chat.id, steps=steps, summary='test')
        assert executor.confirm(plan.id, dummy_user, token) == 'confirmed'
        return executor.run(plan.id), discard
    return _run


def notes(chat):
    return ChatMessage.query.filter_by(session_id=chat.id).count()


def test_success_runs_every_step_as_the_user(run, chat, dummy_event):
    end = dummy_event.end_dt
    plan, _ = run('test_note', 'test_move', 'test_external')
    assert plan.status == 'done' and plan.finished_at is not None
    assert notes(chat) == 1 and dummy_event.end_dt == end + timedelta(minutes=10)
    assert [r['created'] for r in plan.result][2] == {'remote_id': 'r1'}
    assert not External.undone
    assert session.user is None  # nobody is left acting afterwards


def test_failure_leaves_nothing_behind(run, chat, dummy_event):
    end = dummy_event.end_dt
    plan, discard = run('test_note', 'test_move', 'test_external', 'test_boom')
    assert plan.status == 'failed' and 'boom' not in plan.error  # internals stay in the log
    assert notes(chat) == 0 and dummy_event.end_dt == end
    assert External.undone == [dummy_event.id]  # the remote side effect was undone
    assert g.email_queue == []  # nothing is mailed for a plan that did not happen
    discard.assert_called_once()


def test_refusal_at_execution_writes_nothing(run, chat):
    plan, _ = run('test_note', 'test_forbidden')
    assert plan.status == 'refused' and plan.error == 'You cannot manage this event'
    assert notes(chat) == 0


def test_only_confirmed_plans_run(chat, dummy_user):
    plan, _ = executor.create_plan(dummy_user, chat.id, steps=[{'n': 1, 'action': 'test_note', 'args': {'text': 'x'}}],
                                   summary='test')
    with pytest.raises(executor.NotConfirmed):
        executor.run(plan.id)
    assert notes(chat) == 0 and ActionPlan.query.get(plan.id).status == 'shown'


def test_refs_pass_results_forward(chat, dummy_user, dummy_event, monkeypatch):
    seen = []

    class Consumer(MoveEvent):
        name = 'test_consumer'

        def execute(self, user, args):
            seen.append(args.event_id)
            return {'created': None}

    class Producer(WriteNote):
        name = 'test_producer'

        def execute(self, user, args):
            return {'created': {'event_id': dummy_event.id}}

    monkeypatch.setitem(actions.ACTIONS, 'test_consumer', Consumer())
    monkeypatch.setitem(actions.ACTIONS, 'test_producer', Producer())
    steps = [{'n': 1, 'action': 'test_producer', 'args': {'text': 'x'}},
             {'n': 2, 'action': 'test_consumer', 'args': {}, 'refs': {'event_id': '$1'}}]
    plan, token = executor.create_plan(dummy_user, chat.id, steps=steps, summary='test')
    executor.confirm(plan.id, dummy_user, token)
    assert executor.run(plan.id).status == 'done' and seen == [dummy_event.id]
