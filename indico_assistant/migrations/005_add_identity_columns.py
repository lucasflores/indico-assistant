"""Add identity columns to chat_sessions table.

Revision ID: 005_add_identity_columns
Revises: 004_create_extracted_documents
Create Date: 2026-01-21

Feature: 016-user-id-passthrough
Task: T001

Columns added to chat_sessions:
- resolved_user_id: User ID resolved from user-provided identity
- identity_source: How identity was determined ('authenticated', 'user_provided', or null)

Notes:
- Both columns are nullable for backwards compatibility
- Index added on resolved_user_id for potential lookups
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005_add_identity_columns'
down_revision = '004_create_extracted_documents'
branch_labels = None
depends_on = None


def upgrade():
    """Add identity tracking columns to chat_sessions."""
    # Add resolved_user_id column (nullable integer)
    op.add_column(
        'chat_sessions',
        sa.Column('resolved_user_id', sa.Integer, nullable=True),
        schema='plugin_assistant'
    )
    
    # Add identity_source column (nullable varchar)
    op.add_column(
        'chat_sessions',
        sa.Column('identity_source', sa.String(20), nullable=True),
        schema='plugin_assistant'
    )
    
    # Add check constraint for valid identity_source values
    op.create_check_constraint(
        'ck_chat_sessions_identity_source',
        'chat_sessions',
        "identity_source IS NULL OR identity_source IN ('authenticated', 'user_provided')",
        schema='plugin_assistant'
    )
    
    # Create index on resolved_user_id for potential lookups
    op.create_index(
        'ix_chat_sessions_resolved_user_id',
        'chat_sessions',
        ['resolved_user_id'],
        schema='plugin_assistant'
    )


def downgrade():
    """Remove identity tracking columns from chat_sessions."""
    # Drop index
    op.drop_index(
        'ix_chat_sessions_resolved_user_id',
        table_name='chat_sessions',
        schema='plugin_assistant'
    )
    
    # Drop check constraint
    op.drop_constraint(
        'ck_chat_sessions_identity_source',
        'chat_sessions',
        schema='plugin_assistant'
    )
    
    # Drop columns
    op.drop_column('chat_sessions', 'identity_source', schema='plugin_assistant')
    op.drop_column('chat_sessions', 'resolved_user_id', schema='plugin_assistant')
