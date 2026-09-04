"""create learning progress table

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_progress",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.String(length=120), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("review_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mastered", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "owner_id",
            "document_id",
            name="uq_learning_progress_owner_document",
        ),
    )
    op.create_index(
        "ix_learning_progress_owner_id",
        "learning_progress",
        ["owner_id"],
    )
    op.create_index(
        "ix_learning_progress_document_id",
        "learning_progress",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_table("learning_progress")
