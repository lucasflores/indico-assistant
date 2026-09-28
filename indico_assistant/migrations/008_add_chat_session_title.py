"""Add chat_sessions.title (renaming conversations in the Past Chats sidebar).

Revision ID: 008_add_chat_session_title
Revises: 007_create_action_plans
Create Date: 2026-09-28

Feature: 020-chat-persistence
"""

import sqlalchemy as sa
from alembic import op


revision = '008_add_chat_session_title'
down_revision = '007_create_action_plans'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_sessions', sa.Column('title', sa.String(200), nullable=True), schema='plugin_assistant')


def downgrade():
    op.drop_column('chat_sessions', 'title', schema='plugin_assistant')
