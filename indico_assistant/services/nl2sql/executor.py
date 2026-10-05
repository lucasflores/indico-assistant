# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Query executor component for NL2SQL pipeline.

Executes validated SQL queries against the database with proper
permission enforcement and row limits.
"""

import re
import time
from typing import TYPE_CHECKING, Any, Callable

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import DataError, ProgrammingError, SQLAlchemyError

from indico_assistant.services.analytics import recorder
from indico_assistant.services.nl2sql import readonly_db
from indico_assistant.services.nl2sql.models import ExecutionResult

if TYPE_CHECKING:
    from indico_assistant.services.nl2sql.readonly_db import QueryContext


# ":name" that SQLAlchemy's text() would take as a bind parameter (not "::" casts, not already escaped)
_BIND_PARAM = re.compile(r"(?<![:\w\\]):(\w+)")


def _escape_colons(sql, params):
    """Keep only our own placeholders as bind parameters.

    text() treats every ":word" as a parameter, even inside a string such as '(:TBD)', so such queries
    failed with a missing-parameter error. Everything that is not a parameter we bind is escaped and
    reaches Postgres unchanged.
    """
    return _BIND_PARAM.sub(lambda m: m.group(0) if m.group(1) in (params or {}) else "\\" + m.group(0), sql)


class ExecutionError(Exception):
    """Execution error raised for invalid execution preconditions."""


TIMEOUT_MESSAGE_PREFIX = "Query timed out after"


def is_timeout_error(message: str | None) -> bool:
    """Statement timeouts must not be sent to the correction loop: the corrected query is just as heavy."""
    text_ = (message or "").lower()
    return "statement timeout" in text_ or text_.startswith(TIMEOUT_MESSAGE_PREFIX.lower())


def _preview(value):
    """A row value as the trace shows it: cut at 500 characters (spec 024 FR-008)."""
    value = value if isinstance(value, (int, float, bool)) or value is None else str(value)
    return value[:500] if isinstance(value, str) else value


class QueryExecutor:
    """Executes validated SQL as the read-only NL2SQL role (see readonly_db).

    Each query runs on its own short read-only transaction, never on Indico's session: a statement
    timeout, the signed per-question context that the row-level security policies read, and a hard
    row cap (the query is wrapped in LIMIT and only max_rows + 1 rows are fetched).
    """

    def __init__(
        self,
        connection_factory: Callable[[], Any] | None = None,
        max_rows: int = 1000,
        timeout_seconds: int = 10,
        signer: Callable[["QueryContext"], str] | None = None,
    ) -> None:
        """
        Args:
            connection_factory: Returns a context-managed SQLAlchemy connection as the read-only role.
            max_rows: Maximum rows to return (FR-024).
            timeout_seconds: Statement timeout (FR-025); the role also has its own.
            signer: Signs the QueryContext for the row policies.
        """
        self._connection_factory = connection_factory  # None: readonly_db defaults
        self._signer = signer
        self._max_rows = max_rows
        self._timeout_seconds = timeout_seconds

    def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        question: str | None = None,
        context: "QueryContext | None" = None,
    ) -> ExecutionResult:
        """Execute a validated SQL query for the user and scope in `context`."""
        with recorder.step("sql", "query") as step:  # spec 024: the query, its rows, and a preview of them
            recorder.text(step, "sql", sql)
            result = self._execute(sql, params, question, context)
            step.row_count = result.row_count
            if result.truncated:
                recorder.update(truncated=True)
            if not result.success:
                step.ok = False
                step.error_code = ("timeout" if (result.error_message or "").startswith(TIMEOUT_MESSAGE_PREFIX)
                                   else "sql_error" if result.correctable else "failed")
            else:
                recorder.text(step, "rows", [{k: _preview(v) for k, v in row.items()} for row in result.rows[:20]])
            return result

    def _execute(self, sql, params, question, context) -> ExecutionResult:
        start_time = time.time()
        params = params or {}

        try:
            if context is None:
                raise ExecutionError("A user context is required to query event data")
            with readonly_db.scoped_connection(context, self._connection_factory, self._signer) as conn:
                conn.execute(text(f"SET LOCAL statement_timeout = {int(self._timeout_seconds * 1000)}"))
                result = conn.execute(text(_escape_colons(self._wrap_limit(sql), params)), params)
                columns = list(result.keys())
                raw_rows = result.fetchmany(self._max_rows + 1)

            truncated = len(raw_rows) > self._max_rows
            rows = [dict(zip(columns, row)) for row in raw_rows[: self._max_rows]]
            return ExecutionResult(
                success=True,
                rows=rows,
                row_count=len(rows),
                columns=columns,
                execution_time_ms=int((time.time() - start_time) * 1000),
                truncated=truncated,
            )

        except SoftTimeLimitExceeded:  # the worker's time limit: the task reports the timeout (spec 024 FR-001)
            raise
        except Exception as e:
            error_msg = str(e)
            if isinstance(e, ExecutionError):
                pass
            elif is_timeout_error(error_msg):
                error_msg = f"{TIMEOUT_MESSAGE_PREFIX} {self._timeout_seconds} seconds"
            elif not isinstance(e, SQLAlchemyError):
                error_msg = f"Unexpected error: {error_msg}"
            return ExecutionResult(
                success=False,
                rows=[],
                row_count=0,
                columns=[],
                execution_time_ms=int((time.time() - start_time) * 1000),
                error_message=error_msg,
                # Only errors in the SQL itself; a timeout (OperationalError) or setup failure would recur.
                correctable=isinstance(e, (ProgrammingError, DataError)),
            )

    def _wrap_limit(self, sql: str) -> str:
        """Cap the rows in SQL whatever the query says (a LIMIT inside it may be missing or huge)."""
        return f"SELECT * FROM ({sql.strip().rstrip(';')}) AS nl2sql_q LIMIT {self._max_rows + 1}"

    @property
    def max_rows(self) -> int:
        """Get the maximum rows limit."""
        return self._max_rows

    @property
    def timeout_seconds(self) -> int:
        """Get the query timeout in seconds."""
        return self._timeout_seconds
