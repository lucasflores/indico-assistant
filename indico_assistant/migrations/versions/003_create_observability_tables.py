"""Create observability tables for Langfuse metrics storage.

Revision ID: 003_create_observability_tables
Revises: 002_create_chat_tables
Create Date: 2026-01-15

Feature: 005-langfuse-observability
Task: T008

Tables created:
- observability_usage_stats: Aggregated usage statistics
- observability_error_records: Recent errors for debugging
- observability_sync_log: Sync job tracking
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON


# revision identifiers, used by Alembic.
revision = '003_create_observability_tables'
down_revision = '002_create_chat_tables'
branch_labels = None
depends_on = None


def upgrade():
    """Create observability tables in plugin_assistant schema."""
    # Ensure UUID extension is available
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # observability_usage_stats table
    op.create_table(
        'observability_usage_stats',
        sa.Column(
            'id',
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('uuid_generate_v4()')
        ),
        sa.Column('period_type', sa.String(20), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('total_queries', sa.Integer, nullable=False, server_default='0'),
        sa.Column('successful_queries', sa.Integer, nullable=False, server_default='0'),
        sa.Column('avg_latency_ms', sa.Float, nullable=True),
        sa.Column('p95_latency_ms', sa.Float, nullable=True),
        sa.Column('error_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('queries_by_intent', JSON, nullable=True),
        sa.Column('total_input_tokens', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_output_tokens', sa.Integer, nullable=False, server_default='0'),
        sa.Column(
            'last_synced_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "period_type IN ('day', 'week', 'month')",
            name='ck_usage_stats_period_type'
        ),
        sa.UniqueConstraint(
            'period_type', 'period_start',
            name='uq_usage_stats_period'
        ),
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_usage_stats_period',
        'observability_usage_stats',
        ['period_type', 'period_start'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_usage_stats_sync',
        'observability_usage_stats',
        ['last_synced_at'],
        schema='plugin_assistant'
    )

    # observability_error_records table
    op.create_table(
        'observability_error_records',
        sa.Column(
            'id',
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('uuid_generate_v4()')
        ),
        sa.Column('correlation_id', sa.String(64), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('error_type', sa.String(100), nullable=False),
        sa.Column('error_message', sa.Text, nullable=False),
        sa.Column('stack_trace', sa.Text, nullable=True),
        sa.Column('user_id_hash', sa.String(64), nullable=True),
        sa.Column(
            'session_id',
            UUID(as_uuid=True),
            sa.ForeignKey(
                'plugin_assistant.chat_sessions.id',
                ondelete='SET NULL'
            ),
            nullable=True
        ),
        sa.Column('langfuse_trace_id', sa.String(64), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        ),
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_error_record_timestamp',
        'observability_error_records',
        [sa.text('timestamp DESC')],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_error_record_type',
        'observability_error_records',
        ['error_type'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_error_record_correlation',
        'observability_error_records',
        ['correlation_id'],
        schema='plugin_assistant'
    )

    # observability_sync_log table
    op.create_table(
        'observability_sync_log',
        sa.Column(
            'id',
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('uuid_generate_v4()')
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('traces_processed', sa.Integer, nullable=False, server_default='0'),
        sa.Column('stats_updated', sa.Integer, nullable=False, server_default='0'),
        sa.Column('errors_recorded', sa.Integer, nullable=False, server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default="'running'"),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name='ck_sync_log_status'
        ),
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_sync_log_started',
        'observability_sync_log',
        [sa.text('started_at DESC')],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_sync_log_status',
        'observability_sync_log',
        ['status'],
        schema='plugin_assistant'
    )


def downgrade():
    """Drop observability tables."""
    op.drop_table('observability_sync_log', schema='plugin_assistant')
    op.drop_table('observability_error_records', schema='plugin_assistant')
    op.drop_table('observability_usage_stats', schema='plugin_assistant')
