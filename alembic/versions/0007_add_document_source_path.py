"""add document source path

Revision ID: 0007_add_document_source_path
Revises: 0006_add_chunk_page_number
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_add_document_source_path"
down_revision: str | None = "0006_add_chunk_page_number"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("source_path", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "source_path")
