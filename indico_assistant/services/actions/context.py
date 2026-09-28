"""Who the assistant acts as, and in which timezone (research R1, R11)."""

from contextlib import contextmanager

import pytz
from flask import g, has_request_context, session

from indico.core.config import config
from indico.util.date_time import now_utc


@contextmanager
def acting_as(user):
    """Run Indico code as ``user`` outside a web request: ``session.user`` is that user inside the block.

    Indico's operations and some permission checks (``Contribution.can_manage``) read ``session.user``, so
    planning and execution both run in here. Needs a request context (a Celery task declared with
    ``request_context=True``). ``session.set_session_user`` cannot be used: it first looks up the current
    user, which caches "nobody" for the rest of the request (``memoize_request``).
    """
    if not has_request_context():
        raise RuntimeError('acting_as needs a request context (celery.task(request_context=True))')
    if user.is_deleted or user.is_blocked:
        raise PermissionError(f'{user} cannot act: deleted or blocked')
    previous = {key: session[key] for key in ('_user_id', '_lang', '_timezone') if key in session}
    session['_user_id'] = user.id
    session.lang = user.settings.get('lang') or config.DEFAULT_LOCALE
    session.timezone = user_timezone(user).zone
    g.pop('memoize_cache', None)
    if session.user != user:
        raise RuntimeError(f'Could not act as {user}')
    try:
        yield user
    finally:
        for key in ('_user_id', '_lang', '_timezone'):
            session.pop(key, None)
        session.update(previous)
        g.pop('memoize_cache', None)


def user_timezone(user):
    """The timezone the user reads and writes times in."""
    return pytz.timezone(user.settings.get('timezone') or config.DEFAULT_TIMEZONE)


def local_today(user):
    return now_utc().astimezone(user_timezone(user)).date()


def fence(text):
    """Text from Indico for a prompt: marked as data (FR-017), and unable to close its own fence."""
    return '<context>\n' + str(text).replace('<', '‹').replace('>', '›') + '\n</context>'
