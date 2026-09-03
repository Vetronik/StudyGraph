"""add persistent chunk embeddings

Revision ID: 0011_add_chunk_embeddings
Revises: 0010_add_document_content_hash
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_add_chunk_embeddings"
down_revision: str | None = "0010_add_document_content_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN embedding vector(64)"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_cosine "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_cosine")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
