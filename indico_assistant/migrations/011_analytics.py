"""Create the analytics tables (turns, turn_steps, turn_texts) and drop Langfuse's three.

Revision ID: 011_analytics
Revises: 010_create_connections
Create Date: 2026-10-02

Feature: 024-assistant-analytics
"""

import importlib

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = '011_analytics'
down_revision = '010_create_connections'
branch_labels = None
depends_on = None

SCHEMA = 'plugin_assistant'


def upgrade():
    op.create_table(
        'turns',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('job_id', sa.String(32), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=True),
        sa.Column('session_id', UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('message_id', UUID(as_uuid=True), nullable=True),
        sa.Column('answer_id', UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('event_id', sa.Integer(), nullable=True),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('private', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.String(24), nullable=True),
        sa.Column('error_code', sa.String(48), nullable=True),
        sa.Column('route', sa.String(16), nullable=True),
        sa.Column('decided_by', sa.String(16), nullable=True),
        sa.Column('jev_confidence', sa.Float(), nullable=True),
        sa.Column('fallback', sa.String(48), nullable=True),
        sa.Column('llm_calls', sa.SmallInteger(), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(12, 6), nullable=True),
        sa.Column('unpriced_calls', sa.SmallInteger(), nullable=True),
        sa.Column('intent', sa.String(48), nullable=True),
        sa.Column('corrections', sa.SmallInteger(), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.Column('truncated', sa.Boolean(), nullable=True),
        sa.Column('sql_ms', sa.Integer(), nullable=True),
        sa.Column('plan_id', UUID(as_uuid=True), nullable=True),
        sa.Column('tool_calls', sa.SmallInteger(), nullable=True),
        sa.Column('rating', sa.SmallInteger(), nullable=True),
        sa.Column('record', JSONB(), nullable=True),
        schema=SCHEMA,
    )
    op.create_index('ix_turns_user_started', 'turns', ['user_id', 'started_at'], schema=SCHEMA)
    op.create_index('ix_turns_unfinished', 'turns', ['started_at'], schema=SCHEMA,
                    postgresql_where=sa.text('finished_at IS NULL'))
    op.create_table(
        'turn_steps',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('turn_id', sa.BigInteger(), sa.ForeignKey(f'{SCHEMA}.turns.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('seq', sa.SmallInteger(), nullable=False),
        sa.Column('parent_seq', sa.SmallInteger(), nullable=True),
        sa.Column('kind', sa.String(8), nullable=False),
        sa.Column('stage', sa.String(48), nullable=True),
        sa.Column('name', sa.String(64), nullable=True),
        sa.Column('offset_ms', sa.Integer(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('ok', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('error_code', sa.String(48), nullable=True),
        sa.Column('requested_model', sa.String(128), nullable=True),
        sa.Column('served_model', sa.String(128), nullable=True),
        sa.Column('ibis_chosen', sa.String(128), nullable=True),
        sa.Column('ibis_dial', sa.String(32), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(12, 6), nullable=True),
        sa.Column('attempts', sa.SmallInteger(), nullable=True),
        sa.Column('http_errors', ARRAY(sa.SmallInteger()), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.UniqueConstraint('turn_id', 'seq'),
        schema=SCHEMA,
    )
    op.create_table(
        'turn_texts',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('turn_id', sa.BigInteger(), sa.ForeignKey(f'{SCHEMA}.turns.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('seq', sa.SmallInteger(), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('cut', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
                  index=True),
        sa.UniqueConstraint('turn_id', 'seq', 'kind'),
        schema=SCHEMA,
    )
    # Langfuse's tables (feature 005, never wired: always empty), in 003's own order
    op.drop_table('observability_sync_log', schema=SCHEMA)
    op.drop_table('observability_error_records', schema=SCHEMA)
    op.drop_table('observability_usage_stats', schema=SCHEMA)


def downgrade():
    importlib.import_module('indico_assistant.migrations.003_create_observability_tables').upgrade()
    op.drop_table('turn_texts', schema=SCHEMA)
    op.drop_table('turn_steps', schema=SCHEMA)
    op.drop_table('turns', schema=SCHEMA)
