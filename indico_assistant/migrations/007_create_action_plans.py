"""Create action_plans table (chat actions).

Revision ID: 007_create_action_plans
Revises: 006_add_partial_sync_status
Create Date: 2026-09-27

Feature: 019-chat-actions
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = '007_create_action_plans'
down_revision = '006_add_partial_sync_status'
branch_labels = None
depends_on = None

STATUSES = ('shown', 'confirmed', 'running', 'done', 'failed', 'refused', 'cancelled', 'superseded', 'expired')


def upgrade():
    op.create_table(
        'action_plans',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_id', UUID(as_uuid=True),
                  sa.ForeignKey('plugin_assistant.chat_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message_id', UUID(as_uuid=True),
                  sa.ForeignKey('plugin_assistant.chat_messages.id', ondelete='SET NULL'), nullable=True),
        sa.Column('supersedes_id', UUID(as_uuid=True),
                  sa.ForeignKey('plugin_assistant.action_plans.id', ondelete='SET NULL'), nullable=True),
        sa.Column('undoes_id', UUID(as_uuid=True),
                  sa.ForeignKey('plugin_assistant.action_plans.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='shown'),
        sa.Column('steps', JSONB, nullable=False, server_default='[]'),
        sa.Column('questions', JSONB, nullable=False, server_default='[]'),
        sa.Column('suggestions', JSONB, nullable=False, server_default='[]'),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result', JSONB, nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('llm_calls', JSONB, nullable=False, server_default='[]'),
        sa.Column('draft', JSONB, nullable=True),
        sa.CheckConstraint(f"status IN ({', '.join(repr(s) for s in STATUSES)})", name='valid_status'),
        schema='plugin_assistant',
    )
    op.create_index('ix_action_plans_user_status_finished', 'action_plans', ['user_id', 'status', 'finished_at'],
                    schema='plugin_assistant')
    op.create_index('ix_action_plans_session_created', 'action_plans', ['session_id', 'created_at'],
                    schema='plugin_assistant')


def downgrade():
    op.drop_table('action_plans', schema='plugin_assistant')
