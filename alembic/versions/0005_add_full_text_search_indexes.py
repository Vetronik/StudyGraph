"""add full text search indexes

Revision ID: 0005_add_full_text_search_indexes
Revises: 0004_add_document_owner_id
Create Date: 2026-08-31 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_add_full_text_search_indexes"
down_revision: str | None = "0004_add_document_owner_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_document_chunks_text_fts",
        "document_chunks",
        [sa.text("to_tsvector('simple', text)")],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_documents_filename_fts",
        "documents",
        [sa.text("to_tsvector('simple', filename)")],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_documents_filename_fts", table_name="documents")
    op.drop_index("ix_document_chunks_text_fts", table_name="document_chunks")
