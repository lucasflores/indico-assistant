"""The NL2SQL read-only role against a real database (``indico assistant nl2sql-db-sql`` applied).

Skipped unless ASSISTANT_NL2SQL_DATABASE_URI is set. ASSISTANT_NL2SQL_OWNER_URI (default
``postgresql:///indico``) is the Indico role, used to read the signing secret and the expected rows.
"""

import os

import psycopg2
import psycopg2.errors
import pytest

from indico_assistant.services.nl2sql import readonly_db
from indico_assistant.services.nl2sql.readonly_db import QueryContext


RO_URI = os.environ.get(readonly_db.ENV_URI)
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not RO_URI, reason=f'{readonly_db.ENV_URI} not set')]


@pytest.fixture(scope='module')
def owner():
    conn = psycopg2.connect(os.environ.get('ASSISTANT_NL2SQL_OWNER_URI', 'postgresql:///indico'))
    yield conn
    conn.close()


@pytest.fixture(scope='module')
def sign(owner):
    with owner.cursor() as cur:
        cur.execute('SELECT secret FROM plugin_assistant.nl2sql_secret LIMIT 1')
        secret = cur.fetchone()[0]
    original = readonly_db._get_secret
    readonly_db._get_secret = lambda: secret
    yield readonly_db.sign
    readonly_db._get_secret = original


def scalar(owner, sql):
    with owner.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None


def ro(sql, ctx=None):
    """Run ``sql`` as the read-only role in one transaction; return rows or raise."""
    conn = psycopg2.connect(RO_URI)
    try:
        with conn, conn.cursor() as cur:
            if ctx:
                cur.execute("SELECT set_config('indico_assistant.ctx', %s, true)", (ctx,))
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def refused(sql, ctx, message):
    with pytest.raises(psycopg2.Error) as exc:
        ro(sql, ctx)
    assert message in str(exc.value)


@pytest.fixture(scope='module')
def nobody(sign):
    return sign(QueryContext(user_id=999999, event_id=None, is_admin=False))


def test_context_is_required_and_unforgeable(nobody):
    refused('SELECT count(*) FROM events.events', None, 'no query context')
    refused('SELECT count(*) FROM events.events', '999999::1.deadbeef', 'invalid query context')
    refused("SELECT set_config('indico_assistant.ctx', '1::1.x', true), (SELECT count(*) FROM events.events)",
            nobody, 'invalid query context')


@pytest.mark.parametrize(('sql', 'message'), [
    ('SELECT secret FROM plugin_assistant.nl2sql_secret', 'permission denied'),
    ('SELECT email FROM users.users LIMIT 1', 'permission denied'),
    ('SELECT email FROM events.persons LIMIT 1', 'permission denied'),
    ('SELECT * FROM plugin_assistant.chat_messages LIMIT 1', 'permission denied'),
    ('CREATE TABLE nl2sql_probe (a int)', 'read-only'),
    ('SELECT pg_sleep(12)', 'statement timeout'),
])
def test_role_cannot(nobody, sql, message):
    refused(sql, nobody, message)


def test_role_cannot_kill_other_backends(owner, nobody):
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        ro(f'SELECT pg_terminate_backend({owner.get_backend_pid()})', nobody)


def test_visibility(owner, sign, nobody):
    public = scalar(owner, 'SELECT count(*) FROM events.events WHERE NOT is_deleted AND protection_mode = 1')
    visible = {row[0] for row in ro('SELECT id FROM events.events', nobody)}
    assert len(visible) >= public
    assert not ro('SELECT 1 FROM events.events WHERE is_deleted', nobody)

    protected = scalar(owner, 'SELECT id FROM events.events WHERE NOT is_deleted AND protection_mode = 2 LIMIT 1')
    if protected is None:
        pytest.skip('no protected event in this database')
    assert protected not in visible
    assert ro(f'SELECT count(*) FROM events.contributions WHERE event_id = {protected}', nobody) == [(0,)]

    scoped = sign(QueryContext(user_id=999999, event_id=protected, is_admin=False))
    assert ro('SELECT id FROM events.events', scoped) == [(protected,)]
    admin = sign(QueryContext(user_id=999999, event_id=None, is_admin=True))
    assert ro(f'SELECT count(*) FROM events.events WHERE id = {protected}', admin) == [(1,)]


def test_filtered_vector_search_is_not_cut_short(nobody):
    # Without iterative HNSW scans a filtered search only sees the ~40 nearest chunks overall.
    assert ro("SELECT current_setting('hnsw.iterative_scan', true)", nobody) == [('strict_order',)]
