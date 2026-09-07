"""Add persistent document processing progress.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "processing_phase",
            sa.String(length=30),
            nullable=False,
            server_default="completed",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "processing_progress",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "processing_progress")
    op.drop_column("documents", "processing_phase")
