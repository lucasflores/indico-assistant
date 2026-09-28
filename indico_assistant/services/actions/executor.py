"""Plans: created, revised, confirmed, cancelled and carried out (data-model.md; research R2, R14).

A plan runs only after its owner confirms that exact version (one atomic status change, so a double
click runs it once), and it runs all or nothing: every step inside one savepoint, Indico steps first and
steps that call other systems (Teams) last, with their side effects undone if anything fails.
"""

import hashlib
import logging
import secrets
from contextlib import contextmanager, suppress
from datetime import datetime, UTC

from flask import g
from pydantic_core import to_jsonable_python
from sqlalchemy import func, text

from indico.core.db import db
from indico.modules.events.util import track_location_changes, track_time_changes
from indico.modules.users import User

from indico_assistant.models.action_plan import ActionPlan
from indico_assistant.services import actions
from indico_assistant.services.actions.context import acting_as


logger = logging.getLogger(__name__)

FAILED_MESSAGE = 'Something went wrong while making the changes, so nothing was changed. Please try again.'


class NotConfirmed(Exception):
    """Only confirmed plans run."""


class Refused(Exception):
    """A step's permission check failed at execution time (FR-008); the message is the user-facing reason."""


def _now():
    return datetime.now(UTC)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_plan(user, session_id, *, steps, summary, questions=(), suggestions=(), supersedes=None,
                undoes=None, message_id=None, llm_calls=(), draft=None):
    """Save a plan to show; returns (plan, confirm token). A chat has one plan waiting at most: the new one
    supersedes every other shown plan of the chat."""
    from indico_assistant.models import ChatSession

    token = secrets.token_urlsafe(24)
    # the chat's row lock orders concurrent planners of one chat (two quick messages): the second sees the
    # first one's plan once that has committed, and supersedes it, so two plans are never both confirmable
    ChatSession.query.filter_by(id=session_id).with_for_update().first()
    (ActionPlan.query
     .filter(ActionPlan.session_id == session_id, ActionPlan.status == 'shown')
     .update({'status': 'superseded'}, synchronize_session='fetch'))
    plan = ActionPlan(user_id=user.id, session_id=session_id, steps=list(steps), summary=summary,
                      questions=list(questions), suggestions=list(suggestions), token_hash=_hash(token),
                      supersedes_id=supersedes.id if supersedes else None, undoes_id=undoes.id if undoes else None,
                      message_id=message_id, llm_calls=to_jsonable_python(list(llm_calls)), draft=draft)
    db.session.add(plan)
    db.session.flush()
    return plan, token


def open_plan(session_id):
    """The plan waiting for an answer in this chat, if any."""
    return (ActionPlan.query
            .filter(ActionPlan.session_id == session_id, ActionPlan.status == 'shown', ActionPlan.expires_at > _now())
            .order_by(ActionPlan.created_at.desc())
            .first())


def confirm(plan_id, user, token):
    """'confirmed', or why not: 'not_found', 'invalid_token', 'not_confirmable'. The caller commits."""
    plan = ActionPlan.query.filter_by(id=plan_id, user_id=user.id).first()
    if plan is None:
        return 'not_found'
    if not secrets.compare_digest(plan.token_hash, _hash(token or '')):
        return 'invalid_token'
    return _confirm(plan)


def confirm_typed(plan_id, user):
    """The user typed "yes" in the chat the plan was shown in: their own authenticated message, so no token
    (the token guards the buttons, whose payload comes from the browser)."""
    plan = ActionPlan.query.filter_by(id=plan_id, user_id=user.id).first()
    return 'not_found' if plan is None else _confirm(plan)


def _confirm(plan):
    plan_id = plan.id
    if not plan.can_confirm:
        return 'not_confirmable'
    now = _now()
    confirmed = (ActionPlan.query
                 .filter(ActionPlan.id == plan_id, ActionPlan.status == 'shown', ActionPlan.expires_at > now,
                         func.jsonb_array_length(ActionPlan.questions) == 0)
                 .update({'status': 'confirmed', 'confirmed_at': now}, synchronize_session=False))
    db.session.expire(plan)
    return 'confirmed' if confirmed else 'not_confirmable'  # 0 rows: another request confirmed it first


def cancel(plan_id, user):
    cancelled = (ActionPlan.query
                 .filter_by(id=plan_id, user_id=user.id, status='shown')
                 .update({'status': 'cancelled', 'finished_at': _now()}, synchronize_session=False))
    db.session.expire_all()
    return bool(cancelled)


def run(plan_id, enabled=None):
    """Carry out a confirmed plan as its owner. Needs a request context (the execute_plan task).

    ``enabled``: the actions the admin allows now (the task passes them; an action turned off since the
    plan was confirmed refuses the plan)."""
    plan = ActionPlan.query.get(plan_id)
    if plan is None or plan.status != 'confirmed':
        raise NotConfirmed(plan_id)
    plan.status = 'running'
    plan.started_at = _now()
    db.session.commit()

    g.assistant_rollback_callbacks = []
    g.pop('assistant_new_events', None)
    try:
        user = User.get(plan.user_id, is_deleted=False)
        if user is None:
            raise Refused('Your account is no longer active')
        if enabled is not None and (off := [s['action'] for s in plan.steps if s['action'] not in enabled]):
            raise Refused(f'An administrator turned off {", ".join(sorted(set(off)))} since you confirmed')
        try:
            with acting_as(user):
                results = _execute(plan, user)
        except PermissionError as exc:
            raise Refused(str(exc)) from exc
        # the plan's outcome is committed with its changes: a failed commit leaves neither, and is
        # undone below like a failed step (Teams meeting cancelled), never a plan stuck in 'running'
        _mark(plan, 'done', result=results)
        db.session.commit()
    except Refused as exc:
        _abort()
        return _finish(plan_id, 'refused', error=str(exc))
    except Exception:
        logger.exception('Plan %s failed', plan_id)
        _abort()
        return _finish(plan_id, 'failed', error=FAILED_MESSAGE)
    g.pop('assistant_rollback_callbacks', None)
    return plan


@contextmanager
def _savepoint():
    """A savepoint around the steps: a failure anywhere undoes every step (in tests too, where Indico's
    fixture makes session.rollback a no-op).

    Plain SQL, not ``begin_nested()``: SQLAlchemy reports releasing a nested transaction as a commit, and
    Indico then sends ``after_commit``, so work meant for after the commit (vc_teams moving the Teams
    meeting, attachment indexing) would start before the plan is committed.
    """
    db.session.flush()
    db.session.execute(text('SAVEPOINT assistant_plan'))
    try:
        yield
        db.session.flush()
    except BaseException:
        db.session.execute(text('ROLLBACK TO SAVEPOINT assistant_plan'))
        for obj in list(db.session.new):
            db.session.expunge(obj)
        db.session.expire_all()
        raise
    db.session.execute(text('RELEASE SAVEPOINT assistant_plan'))


def _execute(plan, user):
    results = {}
    # Time and location changes of persistent objects raise unless tracked; tracking also sends the
    # signals vc_teams and reminders follow.
    with _savepoint():
        with track_time_changes(auto_extend=True, user=user), track_location_changes():
            for step in plan.steps:
                action = actions.ACTIONS[step['action']]
                args = action.Args.model_validate({**step['args'], **_resolve_refs(step, results)})
                if reason := action.check(user, args):
                    raise Refused(reason)
                outcome = action.execute(user, args) or {}
                results[step['n']] = {'n': step['n'], 'action': step['action'], 'created': outcome.get('created'),
                                      'before': outcome.get('before'), 'after': outcome.get('after'),
                                      **({'skipped': outcome['skipped']} if outcome.get('skipped') else {})}
    return to_jsonable_python(list(results.values()))


def _resolve_refs(step, results):
    resolved = {}
    for arg, ref in (step.get('refs') or {}).items():
        n, key = actions.parse_ref(ref)
        resolved[arg] = (results[n]['created'] or {})[key or arg]
    return resolved


def _abort():
    db.session.rollback()
    for callback in reversed(g.pop('assistant_rollback_callbacks', [])):
        try:
            callback()
        except Exception:
            logger.exception('Undoing a side effect of a failed plan failed')
    if 'email_queue' in g:
        g.email_queue = []  # nothing is mailed about changes that did not happen; queueing stays on
    _discard_vc_pending()


def _discard_vc_pending():
    try:
        from indico_vc_teams.plugin import discard_pending
    except ImportError:
        return
    with suppress(Exception):
        discard_pending()


def _finish(plan_id, status, *, error=None, result=None):
    plan = ActionPlan.query.get(plan_id)
    _mark(plan, status, error=error, result=result)
    db.session.commit()
    return plan


def _mark(plan, status, *, error=None, result=None):
    plan.status = status
    plan.error = error
    plan.result = result
    plan.finished_at = _now()
