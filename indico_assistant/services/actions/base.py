"""What every chat action is made of (data-model.md, "Action").

An action mirrors one Indico page: ``check`` refuses exactly when that page would, ``execute`` does what
the page does through Indico's own operations, and never commits (the executor owns the transaction).
"""

from datetime import datetime
from typing import ClassVar

from flask import g
from pydantic import BaseModel, ConfigDict, field_validator


class ActionArgs(BaseModel):
    """Resolved arguments: ids and timezone-aware datetimes, never names."""

    model_config = ConfigDict(extra='forbid')

    @field_validator('*')
    @classmethod
    def _aware(cls, value):
        if isinstance(value, datetime) and value.tzinfo is None:
            raise ValueError('datetimes must have a timezone')
        return value


class Action:
    name: ClassVar[str]
    Args: ClassVar[type[ActionArgs]]
    #: What it does, as one plain phrase for the capability list (spec 022): "create a meeting (...)".
    summary: ClassVar[str]
    # Runs after every Indico step (it talks to another system, e.g. Teams); it undoes itself through
    # on_rollback if the plan fails later.
    external: ClassVar[bool] = False

    def check(self, user, args):
        """Why ``user`` may not do this (the Indico page's reason), or None."""
        raise NotImplementedError

    def available(self, user, event=None, category=None):
        """Why ``user`` cannot do this at all here, or None (the capability list, spec 022 FR-009).

        ``event``: on that event's page; ``category``: in that category; neither: anywhere the chat can reach, i.e.
        the meetings it finds by name (from a month ago on) and the categories it offers. Built from the helpers
        ``check`` uses, so a reason here means ``check`` refuses too (tests/integration/actions/test_availability.py).
        """
        raise NotImplementedError

    def describe(self, args):
        """(plain-language description, [side effects]) for the plan the user confirms."""
        raise NotImplementedError

    def execute(self, user, args):
        """Do it; returns ``{'created': {...} | None, 'before': {...} | None, 'after': {...} | None}``."""
        raise NotImplementedError

    def revert(self, user, result):
        """Undo a done step (US7)."""
        raise NotImplementedError


def on_rollback(callback):
    """Run ``callback`` if the plan being executed fails: for effects a DB rollback does not undo
    (a Teams meeting, attachment bytes already written to storage)."""
    g.setdefault('assistant_rollback_callbacks', []).append(callback)


def refuse_if_locked(event):
    """The pages refuse every change to a locked event (``check_event_locked``)."""
    if event.is_locked:
        return f'The event “{event.title}” is locked'
    return None


def category_path(category):
    """A category as Indico shows its path."""
    return ' » '.join(category.chain_titles)


def format_dt(dt, tz):
    local = dt.astimezone(tz)
    return f'{local:%a %d %b %Y %H:%M} ({tz.zone})'
