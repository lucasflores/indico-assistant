"""Create connections (a user's connected GitHub account, with its tokens encrypted).

Revision ID: 010_create_connections
Revises: 009_create_issue_reports
Create Date: 2026-09-30

Feature: 023-github-connector
"""

import sqlalchemy as sa
from alembic import op

revision = '010_create_connections'
down_revision = '009_create_issue_reports'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'connections',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False, index=True),
        sa.Column('service', sa.String(20), nullable=False),
        sa.Column('account_id', sa.BigInteger(), nullable=False),
        sa.Column('account_login', sa.String(100), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('access_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('refresh_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('needs_renewal', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint('user_id', 'service'),
        schema='plugin_assistant',
    )


def downgrade():
    op.drop_table('connections', schema='plugin_assistant')
