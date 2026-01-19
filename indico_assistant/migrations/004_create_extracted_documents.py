"""Create extracted_documents table for vector search.

Revision ID: 004_create_extracted_documents
Revises: 003_create_observability_tables
Create Date: 2026-01-16

Feature: 006-vector-search-rag
Task: T007

Tables created:
- extracted_documents: Document chunks with vector embeddings
- document_sync_log: Sync job tracking

Notes:
- pgvector extension is optional; vector column only added if available
- HNSW index created for efficient similarity search
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '004_create_extracted_documents'
down_revision = '003_create_observability_tables'
branch_labels = None
depends_on = None


def check_pgvector():
    """Check if pgvector extension is available."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
    ))
    return result.scalar()


def upgrade():
    """Create document extraction tables in plugin_assistant schema."""
    # Ensure UUID extension is available
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Try to create pgvector extension (may require superuser)
    # If it fails, we'll just skip the vector column
    has_pgvector = False
    try:
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')
        has_pgvector = True
    except Exception:
        has_pgvector = check_pgvector()

    # extracted_documents table
    op.create_table(
        'extracted_documents',
        sa.Column(
            'id',
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('uuid_generate_v4()')
        ),
        sa.Column('event_id', sa.Integer, nullable=False),
        sa.Column('attachment_id', sa.Integer, nullable=False),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('content_text', sa.Text, nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('metadata_json', JSONB, nullable=True),
        sa.Column(
            'extraction_status',
            sa.String(20),
            nullable=False,
            server_default='pending'
        ),
        sa.Column('error_message', sa.Text, nullable=True),
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
        sa.CheckConstraint(
            "extraction_status IN ('pending', 'processing', 'completed', 'failed', 'skipped')",
            name='ck_extracted_documents_status'
        ),
        schema='plugin_assistant'
    )

    # Add vector column if pgvector available
    if has_pgvector:
        op.execute('''
            ALTER TABLE plugin_assistant.extracted_documents
            ADD COLUMN embedding vector(384)
        ''')

        # Create HNSW index for similarity search
        # Parameters: m=16 (connections per layer), ef_construction=64 (build quality)
        op.execute('''
            CREATE INDEX ix_extracted_documents_embedding
            ON plugin_assistant.extracted_documents
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        ''')

    # Create other indexes
    op.create_index(
        'ix_extracted_documents_event',
        'extracted_documents',
        ['event_id'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_extracted_documents_attachment',
        'extracted_documents',
        ['attachment_id'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_extracted_documents_hash',
        'extracted_documents',
        ['content_hash'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_extracted_documents_event_attachment_chunk',
        'extracted_documents',
        ['event_id', 'attachment_id', 'chunk_index'],
        unique=True,
        schema='plugin_assistant'
    )

    # document_sync_log table
    op.create_table(
        'document_sync_log',
        sa.Column(
            'id',
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('uuid_generate_v4()')
        ),
        sa.Column('event_id', sa.Integer, nullable=True),
        sa.Column(
            'started_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        ),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'documents_processed',
            sa.Integer,
            nullable=False,
            server_default='0'
        ),
        sa.Column(
            'chunks_created',
            sa.Integer,
            nullable=False,
            server_default='0'
        ),
        sa.Column(
            'errors_count',
            sa.Integer,
            nullable=False,
            server_default='0'
        ),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name='ck_document_sync_log_status'
        ),
        schema='plugin_assistant'
    )

    op.create_index(
        'ix_document_sync_log_started',
        'document_sync_log',
        ['started_at'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_document_sync_log_event',
        'document_sync_log',
        ['event_id'],
        schema='plugin_assistant'
    )


def downgrade():
    """Drop document extraction tables."""
    op.drop_table('document_sync_log', schema='plugin_assistant')
    op.drop_table('extracted_documents', schema='plugin_assistant')