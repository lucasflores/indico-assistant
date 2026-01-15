# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Unit tests for SQLValidator component."""

from unittest.mock import MagicMock

import pytest

from indico_assistant.services.nl2sql.validator import SQLValidator


@pytest.fixture
def mock_schema_context() -> MagicMock:
    """Create a mock schema context."""
    context = MagicMock()
    # By default, allow all tables
    context.is_table_allowed.return_value = True
    context.get_all_allowed_tables.return_value = [
        "events.events",
        "events.contributions",
        "events.persons",
        "events.registrations",
    ]
    return context


@pytest.fixture
def validator(mock_schema_context: MagicMock) -> SQLValidator:
    """Create a validator instance."""
    return SQLValidator(schema_context=mock_schema_context)


class TestSQLValidatorSelectOnly:
    """Test that only SELECT queries are allowed (FR-012)."""

    def test_valid_select_query(self, validator: SQLValidator) -> None:
        """SELECT query should be valid."""
        result = validator.validate("SELECT * FROM events.events")

        assert result.valid is True
        assert result.violations == []
        assert result.sanitized_sql == "SELECT * FROM events.events"

    def test_select_lowercase(self, validator: SQLValidator) -> None:
        """Lowercase SELECT should be valid."""
        result = validator.validate("select * from events.events")

        assert result.valid is True

    def test_select_with_whitespace(self, validator: SQLValidator) -> None:
        """SELECT with leading whitespace should be valid."""
        result = validator.validate("  SELECT * FROM events.events")

        assert result.valid is True

    def test_insert_rejected(self, validator: SQLValidator) -> None:
        """INSERT query should be rejected."""
        result = validator.validate(
            "INSERT INTO events.events (title) VALUES ('test')"
        )

        assert result.valid is False
        assert "Only SELECT queries are allowed" in result.violations
        assert "DML statement 'INSERT' not allowed" in result.violations

    def test_update_rejected(self, validator: SQLValidator) -> None:
        """UPDATE query should be rejected."""
        result = validator.validate(
            "UPDATE events.events SET title = 'test' WHERE id = 1"
        )

        assert result.valid is False
        assert "Only SELECT queries are allowed" in result.violations
        assert "DML statement 'UPDATE' not allowed" in result.violations

    def test_delete_rejected(self, validator: SQLValidator) -> None:
        """DELETE query should be rejected."""
        result = validator.validate(
            "DELETE FROM events.events WHERE id = 1"
        )

        assert result.valid is False
        assert "Only SELECT queries are allowed" in result.violations
        assert "DML statement 'DELETE' not allowed" in result.violations


class TestSQLValidatorDDLRejection:
    """Test DDL keyword rejection (FR-013)."""

    def test_create_rejected(self, validator: SQLValidator) -> None:
        """CREATE statement should be rejected."""
        result = validator.validate(
            "CREATE TABLE test (id INT)"
        )

        assert result.valid is False
        assert "DDL statement 'CREATE' not allowed" in result.violations

    def test_drop_rejected(self, validator: SQLValidator) -> None:
        """DROP statement should be rejected."""
        result = validator.validate(
            "DROP TABLE events.events"
        )

        assert result.valid is False
        assert "DDL statement 'DROP' not allowed" in result.violations

    def test_alter_rejected(self, validator: SQLValidator) -> None:
        """ALTER statement should be rejected."""
        result = validator.validate(
            "ALTER TABLE events.events ADD COLUMN test INT"
        )

        assert result.valid is False
        assert "DDL statement 'ALTER' not allowed" in result.violations

    def test_truncate_rejected(self, validator: SQLValidator) -> None:
        """TRUNCATE statement should be rejected."""
        result = validator.validate(
            "TRUNCATE TABLE events.events"
        )

        assert result.valid is False
        assert "DDL statement 'TRUNCATE' not allowed" in result.violations

    def test_created_at_allowed(self, validator: SQLValidator) -> None:
        """Column named 'created_at' should NOT trigger CREATE rejection."""
        result = validator.validate(
            "SELECT created_at FROM events.events"
        )

        assert result.valid is True
        assert "DDL statement 'CREATE' not allowed" not in result.violations


class TestSQLValidatorDMLRejection:
    """Test DML keyword rejection (FR-014)."""

    def test_merge_rejected(self, validator: SQLValidator) -> None:
        """MERGE statement should be rejected."""
        result = validator.validate(
            "MERGE INTO events.events USING source ON ..."
        )

        assert result.valid is False
        assert "DML statement 'MERGE' not allowed" in result.violations


class TestSQLValidatorCTERejection:
    """Test CTE rejection (FR-015)."""

    def test_with_cte_rejected(self, validator: SQLValidator) -> None:
        """WITH clause (CTE) should be rejected."""
        result = validator.validate(
            "WITH cte AS (SELECT * FROM events.events) SELECT * FROM cte"
        )

        assert result.valid is False
        assert "'WITH' clause (CTEs) not supported" in result.violations

    def test_within_allowed(self, validator: SQLValidator) -> None:
        """Word 'within' should NOT trigger WITH rejection."""
        result = validator.validate(
            "SELECT * FROM events.events WHERE title LIKE '%within%'"
        )

        assert result.valid is True


class TestSQLValidatorSubqueryRejection:
    """Test subquery rejection (FR-016)."""

    def test_subquery_in_where_rejected(self, validator: SQLValidator) -> None:
        """Subquery in WHERE clause should be rejected."""
        result = validator.validate(
            "SELECT * FROM events.events WHERE id IN (SELECT id FROM temp)"
        )

        assert result.valid is False
        assert "Subqueries (nested SELECT) not supported" in result.violations

    def test_subquery_in_from_rejected(self, validator: SQLValidator) -> None:
        """Subquery in FROM clause should be rejected."""
        result = validator.validate(
            "SELECT * FROM (SELECT * FROM events.events) AS subq"
        )

        assert result.valid is False
        assert "Subqueries (nested SELECT) not supported" in result.violations

    def test_subquery_in_select_rejected(self, validator: SQLValidator) -> None:
        """Subquery in SELECT clause should be rejected."""
        result = validator.validate(
            "SELECT id, (SELECT COUNT(*) FROM events.persons) FROM events.events"
        )

        assert result.valid is False
        assert "Subqueries (nested SELECT) not supported" in result.violations


class TestSQLValidatorWindowFunctionRejection:
    """Test window function rejection (FR-017)."""

    def test_over_clause_rejected(self, validator: SQLValidator) -> None:
        """OVER clause (window function) should be rejected."""
        result = validator.validate(
            "SELECT id, ROW_NUMBER() OVER (ORDER BY id) FROM events.events"
        )

        assert result.valid is False
        assert "Window functions (OVER clause) not supported" in result.violations

    def test_over_with_partition_rejected(self, validator: SQLValidator) -> None:
        """OVER with PARTITION BY should be rejected."""
        result = validator.validate(
            "SELECT id, SUM(count) OVER (PARTITION BY event_id) FROM events.registrations"
        )

        assert result.valid is False
        assert "Window functions (OVER clause) not supported" in result.violations

    def test_rank_function_rejected(self, validator: SQLValidator) -> None:
        """RANK window function should be rejected."""
        result = validator.validate(
            "SELECT id, RANK() OVER (ORDER BY created_at) FROM events.events"
        )

        assert result.valid is False
        assert "Window functions (OVER clause) not supported" in result.violations


class TestSQLValidatorTableAllowlist:
    """Test table allowlist validation (FR-018)."""

    def test_allowed_table_passes(
        self, mock_schema_context: MagicMock, validator: SQLValidator
    ) -> None:
        """Query using allowed table should pass."""
        mock_schema_context.is_table_allowed.return_value = True

        result = validator.validate("SELECT * FROM events.events")

        assert result.valid is True
        mock_schema_context.is_table_allowed.assert_called()

    def test_disallowed_table_rejected(
        self, mock_schema_context: MagicMock
    ) -> None:
        """Query using disallowed table should be rejected."""
        mock_schema_context.is_table_allowed.return_value = False
        validator = SQLValidator(schema_context=mock_schema_context)

        result = validator.validate("SELECT * FROM secret_table")

        assert result.valid is False
        assert "Table 'secret_table' not in allowed list" in result.violations

    def test_multiple_tables_all_allowed(
        self, mock_schema_context: MagicMock
    ) -> None:
        """Query with multiple allowed tables should pass."""
        mock_schema_context.is_table_allowed.return_value = True
        validator = SQLValidator(schema_context=mock_schema_context)

        result = validator.validate(
            "SELECT e.*, p.name FROM events.events e "
            "JOIN events.persons p ON e.id = p.event_id"
        )

        assert result.valid is True
        assert "events.events" in result.tables
        assert "events.persons" in result.tables

    def test_one_disallowed_table_fails(
        self, mock_schema_context: MagicMock
    ) -> None:
        """Query with one disallowed table should fail."""

        def is_allowed(table: str, allowed_list: list[str] | None) -> bool:
            return "users" not in table.lower()

        mock_schema_context.is_table_allowed.side_effect = is_allowed
        validator = SQLValidator(schema_context=mock_schema_context)

        result = validator.validate(
            "SELECT e.*, u.name FROM events.events e "
            "JOIN users.users u ON e.creator_id = u.id"
        )

        assert result.valid is False
        assert "Table 'users.users' not in allowed list" in result.violations


class TestSQLValidatorTableExtraction:
    """Test table name extraction from SQL."""

    def test_extract_from_table(
        self, mock_schema_context: MagicMock
    ) -> None:
        """Extract table from FROM clause."""
        validator = SQLValidator(schema_context=mock_schema_context)
        result = validator.validate("SELECT * FROM events.events")

        assert "events.events" in result.tables

    def test_extract_join_table(
        self, mock_schema_context: MagicMock
    ) -> None:
        """Extract table from JOIN clause."""
        validator = SQLValidator(schema_context=mock_schema_context)
        result = validator.validate(
            "SELECT * FROM events.events e "
            "JOIN events.persons p ON e.id = p.event_id"
        )

        assert "events.events" in result.tables
        assert "events.persons" in result.tables

    def test_extract_multiple_joins(
        self, mock_schema_context: MagicMock
    ) -> None:
        """Extract tables from multiple JOINs."""
        validator = SQLValidator(schema_context=mock_schema_context)
        result = validator.validate(
            "SELECT * FROM events.events e "
            "LEFT JOIN events.contributions c ON e.id = c.event_id "
            "INNER JOIN events.persons p ON c.id = p.contribution_id"
        )

        assert len(result.tables) == 3
        assert "events.events" in result.tables
        assert "events.contributions" in result.tables
        assert "events.persons" in result.tables

    def test_no_duplicate_tables(
        self, mock_schema_context: MagicMock
    ) -> None:
        """Same table used multiple times should appear once."""
        validator = SQLValidator(schema_context=mock_schema_context)
        result = validator.validate(
            "SELECT * FROM events.events e1 "
            "JOIN events.events e2 ON e1.parent_id = e2.id"
        )

        # Should have only one entry for events.events
        assert result.tables.count("events.events") == 1


class TestSQLValidatorTransactionRejection:
    """Test transaction keyword rejection."""

    def test_commit_rejected(self, validator: SQLValidator) -> None:
        """COMMIT statement should be rejected."""
        result = validator.validate("COMMIT")

        assert result.valid is False
        assert "Transaction statement 'COMMIT' not allowed" in result.violations

    def test_rollback_rejected(self, validator: SQLValidator) -> None:
        """ROLLBACK statement should be rejected."""
        result = validator.validate("ROLLBACK")

        assert result.valid is False
        assert "Transaction statement 'ROLLBACK' not allowed" in result.violations

    def test_savepoint_rejected(self, validator: SQLValidator) -> None:
        """SAVEPOINT statement should be rejected."""
        result = validator.validate("SAVEPOINT my_savepoint")

        assert result.valid is False
        assert "Transaction statement 'SAVEPOINT' not allowed" in result.violations


class TestSQLValidatorValidationResult:
    """Test ValidationResult structure."""

    def test_valid_query_has_sanitized_sql(
        self, validator: SQLValidator
    ) -> None:
        """Valid query should have sanitized_sql set."""
        sql = "SELECT * FROM events.events WHERE id = 1"
        result = validator.validate(sql)

        assert result.valid is True
        assert result.sanitized_sql == sql
        assert result.sql == sql

    def test_invalid_query_no_sanitized_sql(
        self, validator: SQLValidator
    ) -> None:
        """Invalid query should have sanitized_sql as None."""
        result = validator.validate("DROP TABLE events.events")

        assert result.valid is False
        assert result.sanitized_sql is None

    def test_multiple_violations_collected(
        self, mock_schema_context: MagicMock
    ) -> None:
        """Multiple violations should all be collected."""
        mock_schema_context.is_table_allowed.return_value = False
        validator = SQLValidator(schema_context=mock_schema_context)

        result = validator.validate(
            "INSERT INTO secret_table SELECT * FROM (SELECT * FROM temp)"
        )

        assert result.valid is False
        assert len(result.violations) >= 3  # INSERT, subquery, not allowed table


class TestSQLValidatorAllowedTablesConfig:
    """Test custom allowed tables configuration."""

    def test_custom_allowed_tables(
        self, mock_schema_context: MagicMock
    ) -> None:
        """Validator should use custom allowed tables if provided."""
        custom_tables = ["events.events", "events.contributions"]
        validator = SQLValidator(
            schema_context=mock_schema_context,
            allowed_tables=custom_tables,
        )

        validator.validate("SELECT * FROM events.events")

        # Verify schema_context was called with custom tables
        mock_schema_context.is_table_allowed.assert_called_with(
            "events.events", custom_tables
        )

    def test_get_allowed_tables(
        self, mock_schema_context: MagicMock
    ) -> None:
        """get_allowed_tables should return schema context's allowed tables."""
        expected_tables = ["events.events", "events.persons"]
        mock_schema_context.get_all_allowed_tables.return_value = expected_tables
        validator = SQLValidator(schema_context=mock_schema_context)

        result = validator.get_allowed_tables()

        assert result == expected_tables


class TestSQLValidatorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_query(self, validator: SQLValidator) -> None:
        """Empty query should fail."""
        result = validator.validate("")

        assert result.valid is False
        assert "Only SELECT queries are allowed" in result.violations

    def test_whitespace_only_query(self, validator: SQLValidator) -> None:
        """Whitespace-only query should fail."""
        result = validator.validate("   \n\t  ")

        assert result.valid is False
        assert "Only SELECT queries are allowed" in result.violations

    def test_comment_only_query(self, validator: SQLValidator) -> None:
        """Comment-only query should fail."""
        result = validator.validate("-- SELECT * FROM events.events")

        assert result.valid is False
        assert "Only SELECT queries are allowed" in result.violations

    def test_multiline_select(self, validator: SQLValidator) -> None:
        """Multiline SELECT should be valid."""
        result = validator.validate("""
            SELECT
                id,
                title,
                created_at
            FROM events.events
            WHERE id = 1
        """)

        assert result.valid is True

    def test_complex_valid_query(
        self, mock_schema_context: MagicMock
    ) -> None:
        """Complex valid query should pass."""
        mock_schema_context.is_table_allowed.return_value = True
        validator = SQLValidator(schema_context=mock_schema_context)

        result = validator.validate("""
            SELECT
                e.id,
                e.title,
                COUNT(c.id) as contribution_count,
                AVG(r.score) as avg_score
            FROM events.events e
            LEFT JOIN events.contributions c ON e.id = c.event_id
            LEFT JOIN events.registrations r ON e.id = r.event_id
            WHERE e.created_at > '2024-01-01'
            GROUP BY e.id, e.title
            HAVING COUNT(c.id) > 0
            ORDER BY avg_score DESC
            LIMIT 10
        """)

        assert result.valid is True
