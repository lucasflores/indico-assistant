"""Add PARTIAL status to document_sync_log check constraint.

Revision ID: 006_add_partial_sync_status
Revises: 005_add_identity_columns
"""

from alembic import op


# revision identifiers, used by Alembic
revision = '006_add_partial_sync_status'
down_revision = '005_add_identity_columns'
branch_labels = None
depends_on = None


def upgrade():
    """Add 'partial' to the SyncStatus check constraint."""
    op.execute("""
        ALTER TABLE plugin_assistant.document_sync_log 
        DROP CONSTRAINT IF EXISTS ck_document_sync_log_ck_document_sync_log_status
    """)
    
    op.execute("""
        ALTER TABLE plugin_assistant.document_sync_log
        ADD CONSTRAINT ck_document_sync_log_ck_document_sync_log_status
        CHECK (status IN ('running', 'completed', 'partial', 'failed'))
    """)


def downgrade():
    """Revert to original SyncStatus values."""
    op.execute("""
        ALTER TABLE plugin_assistant.document_sync_log 
        DROP CONSTRAINT IF EXISTS ck_document_sync_log_ck_document_sync_log_status
    """)
    
    op.execute("""
        ALTER TABLE plugin_assistant.document_sync_log
        ADD CONSTRAINT ck_document_sync_log_ck_document_sync_log_status
        CHECK (status IN ('running', 'completed', 'failed'))
    """)
