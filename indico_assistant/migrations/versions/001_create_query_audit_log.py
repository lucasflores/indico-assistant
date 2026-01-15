"""Alembic migration for query_audit_log table (T048/US5).

Revision ID: 001_create_query_audit_log
Create Date: 2024-01-15

Creates the query_audit_log table in plugin_assistant schema for NL2SQL audit logging.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = "001_create_query_audit_log"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create query_audit_log table."""
    # Ensure schema exists
    op.execute("CREATE SCHEMA IF NOT EXISTS plugin_assistant")
    
    op.create_table(
        "query_audit_log",
        # Primary key
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        
        # User information
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        
        # Query information
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(64), nullable=True),
        sa.Column("intent_confidence", sa.Float(), nullable=True),
        
        # Generated SQL (FR-031: results NOT stored)
        sa.Column("generated_sql", sa.Text(), nullable=True),
        
        # Execution metrics
        sa.Column("execution_time_ms", sa.Float(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        
        # Status
        sa.Column("success", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("error_message", sa.Text(), nullable=True),
        
        # Validation tracking
        sa.Column("validation_rejection_reason", sa.String(128), nullable=True),
        
        # Error correction tracking
        sa.Column("correction_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("was_corrected", sa.Boolean(), nullable=False, server_default="false"),
        
        # Cache tracking
        sa.Column("cached", sa.Boolean(), nullable=False, server_default="false"),
        
        # Security audit
        sa.Column("ip_address", sa.String(45), nullable=True),
        
        # Primary key constraint
        sa.PrimaryKeyConstraint("id"),
        
        # Table in plugin_assistant schema
        schema="plugin_assistant",
    )
    
    # Create indexes for common query patterns
    op.create_index(
        "ix_query_audit_log_created_at",
        "query_audit_log",
        ["created_at"],
        schema="plugin_assistant",
    )
    op.create_index(
        "ix_query_audit_log_user_id",
        "query_audit_log",
        ["user_id"],
        schema="plugin_assistant",
    )
    op.create_index(
        "ix_query_audit_log_session_id",
        "query_audit_log",
        ["session_id"],
        schema="plugin_assistant",
    )
    op.create_index(
        "ix_query_audit_log_intent",
        "query_audit_log",
        ["intent"],
        schema="plugin_assistant",
    )
    
    # Create composite index for common filtering
    op.create_index(
        "ix_query_audit_log_user_created",
        "query_audit_log",
        ["user_id", "created_at"],
        schema="plugin_assistant",
    )


def downgrade() -> None:
    """Drop query_audit_log table."""
    op.drop_index(
        "ix_query_audit_log_user_created",
        table_name="query_audit_log",
        schema="plugin_assistant",
    )
    op.drop_index(
        "ix_query_audit_log_intent",
        table_name="query_audit_log",
        schema="plugin_assistant",
    )
    op.drop_index(
        "ix_query_audit_log_session_id",
        table_name="query_audit_log",
        schema="plugin_assistant",
    )
    op.drop_index(
        "ix_query_audit_log_user_id",
        table_name="query_audit_log",
        schema="plugin_assistant",
    )
    op.drop_index(
        "ix_query_audit_log_created_at",
        table_name="query_audit_log",
        schema="plugin_assistant",
    )
    op.drop_table("query_audit_log", schema="plugin_assistant")
