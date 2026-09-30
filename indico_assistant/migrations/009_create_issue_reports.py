"""Create issue_reports (reports sent from the chat, and the team's status on them).

Revision ID: 009_create_issue_reports
Revises: 008_add_chat_session_title
Create Date: 2026-09-30

Feature: 021-issue-reports
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = '009_create_issue_reports'
down_revision = '008_add_chat_session_title'
branch_labels = None
depends_on = None

CATEGORIES = ('bug', 'feature', 'wrong_answer')
STATUSES = ('open', 'under_review', 'closed')


def _in(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade():
    op.create_table(
        'issue_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False, index=True),
        sa.Column('form_key', UUID(as_uuid=True), nullable=False),
        sa.Column('category', sa.String(20), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('copy', JSONB, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(_in('category', CATEGORIES), name='valid_category'),
        sa.CheckConstraint(_in('status', STATUSES), name='valid_status'),
        sa.UniqueConstraint('user_id', 'form_key'),
        schema='plugin_assistant',
    )
    op.create_index('ix_issue_reports_status_created', 'issue_reports', ['status', 'created_at'],
                    schema='plugin_assistant')


def downgrade():
    op.drop_table('issue_reports', schema='plugin_assistant')
