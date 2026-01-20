# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
SQL validator component for NL2SQL pipeline.

Validates generated SQL against security rules and allowed tables.
"""

import re
from typing import Pattern

from indico_assistant.services.nl2sql.models import ValidationResult
from indico_assistant.services.nl2sql.schema import SchemaContext


class SQLValidator:
    """Validates SQL queries against security rules."""

    # Forbidden SQL patterns (FR-012-018)
    FORBIDDEN_KEYWORDS = {
        "ddl": ["CREATE", "DROP", "ALTER", "TRUNCATE"],
        "dml": ["INSERT", "UPDATE", "DELETE", "MERGE"],
        "transaction": ["COMMIT", "ROLLBACK", "SAVEPOINT"],
        "advanced": ["WITH"],  # CTEs
    }

    # Pattern to detect subqueries (nested SELECT)
    SUBQUERY_PATTERN: Pattern[str] = re.compile(
        r"\(\s*SELECT\s+", re.IGNORECASE
    )

    # Pattern to detect window functions (OVER clause)
    WINDOW_PATTERN: Pattern[str] = re.compile(
        r"\bOVER\s*\(", re.IGNORECASE
    )

    # Pattern to extract table names from SQL
    # Matches: FROM table, JOIN table, table AS alias
    TABLE_PATTERN: Pattern[str] = re.compile(
        r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_.]*)",
        re.IGNORECASE
    )

    def __init__(
        self,
        schema_context: SchemaContext,
        allowed_tables: list[str] | None = None,
    ) -> None:
        """
        Initialize the validator.

        Args:
            schema_context: Schema context for table validation.
            allowed_tables: Optional explicit list of allowed tables.
        """
        self._schema_context = schema_context
        self._allowed_tables = allowed_tables

    def validate(self, sql: str) -> ValidationResult:
        """
        Validate a SQL query against security rules.

        Checks:
        1. Must be SELECT-only (FR-012)
        2. No DDL keywords (CREATE, DROP, ALTER, TRUNCATE) (FR-013)
        3. No DML keywords (INSERT, UPDATE, DELETE) (FR-014)
        4. No CTEs (WITH clause) (FR-015)
        5. No subqueries (nested SELECT) (FR-016)
        6. No window functions (OVER clause) (FR-017)
        7. All tables in allowlist (FR-018)

        Args:
            sql: The SQL query to validate.

        Returns:
            ValidationResult with validity status and any violations.
        """
        violations: list[str] = []
        sql_upper = sql.upper().strip()

        # Rule 1: Must start with SELECT (FR-012)
        if not sql_upper.startswith("SELECT"):
            violations.append(
                "Only SELECT queries are allowed; please ask for read-only data"
            )

        # Rule 2: No DDL keywords (FR-013)
        for keyword in self.FORBIDDEN_KEYWORDS["ddl"]:
            if self._has_keyword(sql_upper, keyword):
                violations.append(
                    f"DDL statement '{keyword}' not allowed; use read-only queries"
                )

        # Rule 3: No DML keywords (FR-014)
        for keyword in self.FORBIDDEN_KEYWORDS["dml"]:
            if self._has_keyword(sql_upper, keyword):
                violations.append(
                    f"DML statement '{keyword}' not allowed; use read-only queries"
                )

        # Rule 4: No transaction keywords
        for keyword in self.FORBIDDEN_KEYWORDS["transaction"]:
            if self._has_keyword(sql_upper, keyword):
                violations.append(
                    f"Transaction statement '{keyword}' not allowed in read-only queries"
                )

        # Rule 5: No CTEs (WITH clause) (FR-015)
        for keyword in self.FORBIDDEN_KEYWORDS["advanced"]:
            if self._has_keyword(sql_upper, keyword):
                violations.append(
                    f"'{keyword}' clause (CTEs) not supported; use JOINs instead"
                )

        # Rule 6: No subqueries (FR-016)
        if self.SUBQUERY_PATTERN.search(sql):
            violations.append(
                "Subqueries (nested SELECT) not supported; use JOINs instead"
            )

        # Rule 7: No window functions (FR-017)
        if self.WINDOW_PATTERN.search(sql):
            violations.append(
                "Window functions (OVER clause) not supported; use ORDER BY + LIMIT instead"
            )

        # Extract tables from SQL
        tables = self._extract_tables(sql)

        # Rule 8: All tables must be in allowlist (FR-018)
        disallowed_tables = self._check_table_allowlist(tables)
        for table in disallowed_tables:
            violations.append(
                f"Table '{table}' not in allowed list; choose from approved event data"
            )

        return ValidationResult(
            valid=len(violations) == 0,
            sql=sql,
            tables=tables,
            violations=violations,
            sanitized_sql=sql if len(violations) == 0 else None,
        )

    def _has_keyword(self, sql_upper: str, keyword: str) -> bool:
        """
        Check if SQL contains a keyword as a standalone word.

        Uses word boundary matching to avoid false positives
        (e.g., "CREATED_AT" should not match "CREATE").

        Args:
            sql_upper: Uppercase SQL string
            keyword: Keyword to search for

        Returns:
            True if keyword is found as a standalone word.
        """
        pattern = rf"\b{keyword}\b"
        return bool(re.search(pattern, sql_upper))

    def _extract_tables(self, sql: str) -> list[str]:
        """
        Extract table names from SQL query.

        Args:
            sql: The SQL query

        Returns:
            List of table names found in the query.
        """
        matches = self.TABLE_PATTERN.findall(sql)
        # Remove duplicates while preserving order
        seen = set()
        tables = []
        for table in matches:
            table_lower = table.lower()
            if table_lower not in seen:
                seen.add(table_lower)
                tables.append(table)
        return tables

    def _check_table_allowlist(self, tables: list[str]) -> list[str]:
        """
        Check which tables are not in the allowlist.

        Args:
            tables: List of table names to check

        Returns:
            List of tables that are NOT allowed.
        """
        allowed_tables = self._schema_context.get_all_allowed_tables(
            self._allowed_tables
        )
        if not allowed_tables:
            return []
        disallowed = []
        for table in tables:
            if not self._schema_context.is_table_allowed(
                table, self._allowed_tables
            ):
                disallowed.append(table)
        return disallowed

    def get_allowed_tables(self) -> list[str]:
        """Get the list of allowed tables."""
        return self._schema_context.get_all_allowed_tables(self._allowed_tables)
