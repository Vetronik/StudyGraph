"""add document content hash

Revision ID: 0010_add_document_content_hash
Revises: 0009_create_users_table
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_add_document_content_hash"
down_revision: str | None = "0009_create_users_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("content_hash", sa.String(64)))
    op.create_unique_constraint(
        "uq_documents_owner_content_hash",
        "documents",
        ["owner_id", "content_hash"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_documents_owner_content_hash",
        "documents",
        type_="unique",
    )
    op.drop_column("documents", "content_hash")
