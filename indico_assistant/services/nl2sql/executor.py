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

import time
from typing import TYPE_CHECKING, Any, Callable

from sqlalchemy import text
from sqlalchemy.exc import DataError, ProgrammingError, SQLAlchemyError

from indico_assistant.services.nl2sql.models import ExecutionResult

if TYPE_CHECKING:
    from indico_assistant.services.embedding.service import EmbeddingService
    from indico_assistant.services.nl2sql.readonly_db import QueryContext


class ExecutionError(Exception):
    """Execution error raised for invalid execution preconditions."""


TIMEOUT_MESSAGE_PREFIX = "Query timed out after"


def is_timeout_error(message: str | None) -> bool:
    """Statement timeouts must not be sent to the correction loop: the corrected query is just as heavy."""
    text_ = (message or "").lower()
    return "statement timeout" in text_ or text_.startswith(TIMEOUT_MESSAGE_PREFIX.lower())


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
        embedding_service: "EmbeddingService | None" = None,
        signer: Callable[["QueryContext"], str] | None = None,
    ) -> None:
        """
        Args:
            connection_factory: Returns a context-managed SQLAlchemy connection as the read-only role.
            max_rows: Maximum rows to return (FR-024).
            timeout_seconds: Statement timeout (FR-025); the role also has its own.
            signer: Signs the QueryContext for the row policies.
        """
        from indico_assistant.services.nl2sql import readonly_db

        self._connection_factory = connection_factory or readonly_db.connect
        self._signer = signer or readonly_db.sign
        self._max_rows = max_rows
        self._timeout_seconds = timeout_seconds
        self._embedding_service = embedding_service

    def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        question: str | None = None,
        context: "QueryContext | None" = None,
    ) -> ExecutionResult:
        """Execute a validated SQL query for the user and scope in `context`."""
        start_time = time.time()
        params = params or {}

        try:
            if context is None:
                raise ExecutionError("A user context is required to query event data")
            signed_context = self._signer(context)
            params = self._prepare_vector_params(sql, question, params)
            with self._connection_factory() as conn, conn.begin():
                conn.execute(text(f"SET LOCAL statement_timeout = {int(self._timeout_seconds * 1000)}"))
                conn.execute(text("SELECT set_config('indico_assistant.ctx', :ctx, true)"),
                             {"ctx": signed_context})
                result = conn.execute(text(self._wrap_limit(sql)), params)
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

    def _contains_vector_placeholder(self, sql: str) -> bool:
        """Check if SQL contains :query_vector parameter placeholder."""
        return ":query_vector" in sql

    def _prepare_vector_params(
        self,
        sql: str,
        question: str | None,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Prepare parameters with query vector if needed."""
        if not self._contains_vector_placeholder(sql):
            return params

        if self._embedding_service is None:
            raise ExecutionError(
                "Vector search requested but embedding service not available"
            )

        if not question:
            raise ExecutionError(
                "Vector search requested but no question provided for embedding"
            )

        embedding = self._embedding_service.embed_text(question)
        vector_str = "[" + ",".join(str(x) for x in embedding) + "]"

        updated_params = dict(params) if params else {}
        updated_params["query_vector"] = vector_str
        return updated_params

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
