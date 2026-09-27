"""QueryExecutor: runs validated SQL as the read-only NL2SQL role (readonly_db), never on Indico's session."""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from indico_assistant.services.nl2sql.executor import QueryExecutor, is_timeout_error
from indico_assistant.services.nl2sql.readonly_db import QueryContext


CTX = QueryContext(user_id=7, event_id=None, is_admin=False)


class FakeConnection:
    def __init__(self, rows=(), columns=('id', 'title'), error=None):
        self.statements = []
        self._rows, self._columns, self._error = list(rows), list(columns), error

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        if sql.startswith('SELECT * FROM ('):
            if self._error:
                raise self._error
            result = MagicMock()
            result.keys.return_value = self._columns
            result.fetchmany.side_effect = lambda n: self._rows[:n]
            return result
        return MagicMock()

    @contextmanager
    def begin(self):
        yield

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make(conn, **kwargs):
    return QueryExecutor(connection_factory=lambda: conn, signer=lambda ctx: f'signed:{ctx.payload()}', **kwargs)


def test_returns_rows_and_columns():
    conn = FakeConnection(rows=[(1, 'A'), (2, 'B')])
    result = make(conn).execute('SELECT id, title FROM events.events', context=CTX)
    assert result.success and result.row_count == 2 and result.columns == ['id', 'title']
    assert result.rows == [{'id': 1, 'title': 'A'}, {'id': 2, 'title': 'B'}] and not result.truncated


def test_sets_timeout_and_signed_context_before_the_query():
    conn = FakeConnection()
    make(conn, timeout_seconds=12).execute('SELECT id FROM events.events', context=CTX)
    (timeout_sql, _), (ctx_sql, ctx_params), (query_sql, _) = conn.statements
    assert timeout_sql == 'SET LOCAL statement_timeout = 12000'
    assert "set_config('indico_assistant.ctx'" in ctx_sql and ctx_params == {'ctx': 'signed:7::0'}
    assert query_sql.startswith('SELECT * FROM (')


@pytest.mark.parametrize('sql', ['SELECT id FROM events.events;', 'SELECT id FROM events.events LIMIT 5000000',
                                 "SELECT id FROM events.events WHERE title ILIKE '%time limit%'"])
def test_row_cap_wraps_any_query(sql):
    conn = FakeConnection()
    make(conn, max_rows=50).execute(sql, context=CTX)
    query_sql = conn.statements[-1][0]
    assert query_sql == f"SELECT * FROM ({sql.rstrip(';')}) AS nl2sql_q LIMIT 51"


def test_truncates_to_max_rows():
    conn = FakeConnection(rows=[(i, str(i)) for i in range(10)])
    result = make(conn, max_rows=3).execute('SELECT id, title FROM events.events', context=CTX)
    assert result.row_count == 3 and result.truncated


def test_refuses_without_a_context_and_never_connects():
    factory = MagicMock()
    result = QueryExecutor(connection_factory=factory, signer=str).execute('SELECT 1')
    assert not result.success and 'user context is required' in result.error_message and not result.correctable
    factory.assert_not_called()


def test_timeout_is_reported_as_timeout():
    conn = FakeConnection(error=OperationalError('q', {}, Exception('canceling statement due to statement timeout')))
    result = make(conn, timeout_seconds=10).execute('SELECT 1 FROM events.events', context=CTX)
    assert not result.success and result.error_message == 'Query timed out after 10 seconds'
    assert is_timeout_error(result.error_message) and not result.correctable


def test_sql_error_is_returned_and_correctable():
    conn = FakeConnection(error=ProgrammingError('q', {}, Exception('column "nope" does not exist')))
    result = make(conn).execute('SELECT nope FROM events.events', context=CTX)
    assert not result.success and 'does not exist' in result.error_message and result.correctable


@pytest.mark.parametrize('error', [OperationalError('q', {}, Exception('connection refused')), ValueError('boom')])
def test_setup_and_connection_errors_are_not_correctable(error):
    assert not make(FakeConnection(error=error)).execute('SELECT 1', context=CTX).correctable


def test_unexpected_error_is_labelled():
    conn = FakeConnection(error=ValueError('boom'))
    assert make(conn).execute('SELECT 1', context=CTX).error_message == 'Unexpected error: boom'


def test_params_are_passed_through():
    conn = FakeConnection()
    make(conn).execute('SELECT id FROM events.events WHERE id = :event_id', params={'event_id': 3}, context=CTX)
    assert conn.statements[-1][1] == {'event_id': 3}


def test_vector_placeholder_needs_an_embedding_service():
    result = make(FakeConnection()).execute('SELECT 1 ORDER BY x <=> :query_vector', question='q', context=CTX)
    assert not result.success and 'embedding service' in result.error_message


def test_vector_placeholder_is_filled_from_the_question():
    conn = FakeConnection()
    embedder = MagicMock(embed_text=MagicMock(return_value=[0.5, 0.25]))
    make(conn, embedding_service=embedder).execute('SELECT 1 ORDER BY x <=> :query_vector', question='q',
                                                   context=CTX)
    assert conn.statements[-1][1] == {'query_vector': '[0.5,0.25]'}
