"""Create documents and document_chunks; drop extracted_documents and document_sync_log.

Revision ID: 012_documents
Revises: 011_analytics
Create Date: 2026-10-05

Feature: 025-assistant-core (story 2)

There are no users, so the old index is dropped rather than migrated: a sync reads every attachment again.
The downgrade recreates the old tables empty.
"""

import importlib

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

revision = "012_documents"
down_revision = "011_analytics"
branch_labels = None
depends_on = None

SCHEMA = "plugin_assistant"


def upgrade():
    op.create_table(
        "documents",
        sa.Column("attachment_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("event_id", sa.Integer(), nullable=False, index=True),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("outline", JSONB(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('queued', 'reading', 'ready', 'no_text', 'failed', 'unsupported')", name="status"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "attachment_id",
            sa.Integer(),
            sa.ForeignKey(f"{SCHEMA}.documents.attachment_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("offset", sa.Integer(), nullable=False),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("search", TSVECTOR(), nullable=False),
        sa.UniqueConstraint("attachment_id", "chunk_index"),
        schema=SCHEMA,
    )
    op.create_index("ix_document_chunks_search", "document_chunks", ["search"], schema=SCHEMA, postgresql_using="gin")
    # ponytail: no ANN index, an exact scan is fine for thousands of chunks; add HNSW past ~100k
    if op.get_bind().execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar():
        op.execute(f"ALTER TABLE {SCHEMA}.document_chunks ADD COLUMN embedding vector(384)")
    op.drop_table("document_sync_log", schema=SCHEMA)
    op.drop_table("extracted_documents", schema=SCHEMA)


def downgrade():
    op.drop_table("document_chunks", schema=SCHEMA)
    op.drop_table("documents", schema=SCHEMA)
    importlib.import_module("indico_assistant.migrations.004_create_extracted_documents").upgrade()
    importlib.import_module("indico_assistant.migrations.006_add_partial_sync_status").upgrade()
