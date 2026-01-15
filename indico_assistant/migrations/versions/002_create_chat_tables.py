"""Create chat_sessions, chat_messages, feedback_entries tables.

Revision ID: 002_create_chat_tables
Revises: 001_create_query_audit_log
Create Date: 2026-01-14

Feature: 004-chat-api
Task: T001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '002_create_chat_tables'
down_revision = '001_create_query_audit_log'
branch_labels = None
depends_on = None


def upgrade():
    """Create chat tables in plugin_assistant schema."""
    # Ensure UUID extension is available
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # chat_sessions table
    op.create_table(
        'chat_sessions',
        sa.Column(
            'id',
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('uuid_generate_v4()')
        ),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('event_id', sa.Integer, nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        ),
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_chat_sessions_user_id',
        'chat_sessions',
        ['user_id'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_chat_sessions_event_id',
        'chat_sessions',
        ['event_id'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_chat_sessions_updated_at',
        'chat_sessions',
        ['updated_at'],
        schema='plugin_assistant'
    )

    # chat_messages table
    op.create_table(
        'chat_messages',
        sa.Column(
            'id',
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('uuid_generate_v4()')
        ),
        sa.Column(
            'session_id',
            UUID(as_uuid=True),
            sa.ForeignKey(
                'plugin_assistant.chat_sessions.id',
                ondelete='CASCADE'
            ),
            nullable=False
        ),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('metadata_json', JSONB, nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name='ck_chat_messages_role'
        ),
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_chat_messages_session_id',
        'chat_messages',
        ['session_id'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_chat_messages_created_at',
        'chat_messages',
        ['created_at'],
        schema='plugin_assistant'
    )

    # feedback_entries table
    op.create_table(
        'feedback_entries',
        sa.Column(
            'id',
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('uuid_generate_v4()')
        ),
        sa.Column(
            'message_id',
            UUID(as_uuid=True),
            sa.ForeignKey(
                'plugin_assistant.chat_messages.id',
                ondelete='CASCADE'
            ),
            nullable=False
        ),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('feedback_type', sa.String(32), nullable=False),
        sa.Column('value', sa.Text, nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "feedback_type IN ('thumbs_up', 'thumbs_down', 'rating', 'comment')",
            name='ck_feedback_type'
        ),
        sa.UniqueConstraint(
            'message_id', 'user_id', 'feedback_type',
            name='uq_feedback_per_user_type'
        ),
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_feedback_entries_message_id',
        'feedback_entries',
        ['message_id'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_feedback_entries_user_id',
        'feedback_entries',
        ['user_id'],
        schema='plugin_assistant'
    )


def downgrade():
    """Drop chat tables in reverse order."""
    op.drop_table('feedback_entries', schema='plugin_assistant')
    op.drop_table('chat_messages', schema='plugin_assistant')
    op.drop_table('chat_sessions', schema='plugin_assistant')
