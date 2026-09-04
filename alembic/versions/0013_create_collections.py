"""create document collections

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "name",
            name="uq_collections_owner_name",
        ),
    )
    op.create_index("ix_collections_owner_id", "collections", ["owner_id"])
    op.create_table(
        "collection_documents",
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("collection_id", "document_id"),
    )
    op.create_index(
        "ix_collection_documents_document_id",
        "collection_documents",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collection_documents_document_id",
        table_name="collection_documents",
    )
    op.drop_table("collection_documents")
    op.drop_index("ix_collections_owner_id", table_name="collections")
    op.drop_table("collections")
