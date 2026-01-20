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
from sqlalchemy.exc import SQLAlchemyError

from indico_assistant.services.nl2sql.models import ExecutionResult

if TYPE_CHECKING:
    from indico_assistant.services.embedding.service import EmbeddingService


class ExecutionError(Exception):
    """Execution error raised for invalid execution preconditions."""


class QueryExecutor:
    """Executes validated SQL queries."""

    def __init__(
        self,
        db_session_factory: Callable[[], Any],
        max_rows: int = 1000,
        timeout_seconds: int = 30,
        embedding_service: "EmbeddingService | None" = None,
    ) -> None:
        """
        Initialize the executor.

        Args:
            db_session_factory: Factory function to get database session.
            max_rows: Maximum rows to return (FR-024).
            timeout_seconds: Query timeout in seconds (FR-025).
        """
        self._db_session_factory = db_session_factory
        self._max_rows = max_rows
        self._timeout_seconds = timeout_seconds
        self._embedding_service = embedding_service

    def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        question: str | None = None,
    ) -> ExecutionResult:
        """
        Execute a validated SQL query.

        The query is executed in a read-only transaction with timeout
        and row limits applied. Results are converted to a list of
        dictionaries.

        Args:
            sql: The validated SQL query.
            params: Optional query parameters for parameterized queries.

        Returns:
            ExecutionResult with rows or error information.
        """
        start_time = time.time()
        params = params or {}

        try:
            session = self._db_session_factory()

            # Use nested transaction (SAVEPOINT) to isolate query execution
            # from parent transaction. This prevents rollback from affecting
            # chat session/message persistence.
            # Feature 013: Fix transaction isolation for error handling
            with session.begin_nested():
                # Add LIMIT if not present (FR-024)
                sql_with_limit = self._ensure_limit(sql)

                # Prepare vector params if needed
                params = self._prepare_vector_params(
                    sql_with_limit, question, params
                )

                # Set statement timeout (FR-025)
                timeout_ms = self._timeout_seconds * 1000
                session.execute(
                    text(f"SET LOCAL statement_timeout = {timeout_ms}")
                )

                # Execute the query
                result = session.execute(text(sql_with_limit), params)

                # Get column names
                columns = list(result.keys())

                # Fetch results
                raw_rows = result.fetchall()

            # Check if truncated (outside nested transaction)
            truncated = len(raw_rows) >= self._max_rows

            # Convert to list of dicts
            rows = [dict(zip(columns, row)) for row in raw_rows]

            # Limit rows if exceeded
            if len(rows) > self._max_rows:
                rows = rows[: self._max_rows]
                truncated = True

            execution_time = int((time.time() - start_time) * 1000)

            return ExecutionResult(
                success=True,
                rows=rows,
                row_count=len(rows),
                columns=columns,
                execution_time_ms=execution_time,
                truncated=truncated,
            )

        except ExecutionError as e:
            execution_time = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                success=False,
                rows=[],
                row_count=0,
                columns=[],
                execution_time_ms=execution_time,
                error_message=str(e),
            )

        except SQLAlchemyError as e:
            # Nested transaction automatically rolls back to SAVEPOINT
            # No need to call rollback() - prevents affecting parent transaction
            execution_time = int((time.time() - start_time) * 1000)
            error_msg = str(e)

            # Check for timeout
            if "statement timeout" in error_msg.lower():
                error_msg = (
                    f"Query timed out after {self._timeout_seconds} seconds"
                )

            return ExecutionResult(
                success=False,
                rows=[],
                row_count=0,
                columns=[],
                execution_time_ms=execution_time,
                error_message=error_msg,
            )

        except Exception as e:
            # Nested transaction automatically rolls back to SAVEPOINT
            execution_time = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                success=False,
                rows=[],
                row_count=0,
                columns=[],
                execution_time_ms=execution_time,
                error_message=f"Unexpected error: {str(e)}",
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

    def _ensure_limit(self, sql: str) -> str:
        """
        Ensure SQL has a LIMIT clause.

        If the SQL doesn't already have a LIMIT, adds one with max_rows.

        Args:
            sql: The SQL query.

        Returns:
            SQL with LIMIT clause ensured.
        """
        sql_upper = sql.upper()

        # Check if LIMIT already exists
        if "LIMIT" in sql_upper:
            return sql

        # Add LIMIT
        # Handle potential trailing semicolon
        sql_stripped = sql.rstrip().rstrip(";")
        return f"{sql_stripped} LIMIT {self._max_rows}"

    @property
    def max_rows(self) -> int:
        """Get the maximum rows limit."""
        return self._max_rows

    @property
    def timeout_seconds(self) -> int:
        """Get the query timeout in seconds."""
        return self._timeout_seconds
