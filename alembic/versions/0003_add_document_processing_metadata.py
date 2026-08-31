"""add document processing metadata

Revision ID: 0003_add_document_processing_metadata
Revises: 0002_create_document_chunks_table
Create Date: 2026-08-31 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_add_document_processing_metadata"
down_revision: str | None = "0002_create_document_chunks_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "file_size_bytes",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="processed",
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("processing_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "processing_error")
    op.drop_column("documents", "status")
    op.drop_column("documents", "file_size_bytes")
