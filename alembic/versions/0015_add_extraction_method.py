"""Add extraction method diagnostics to documents.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "extraction_method",
            sa.String(length=20),
            nullable=False,
            server_default="text",
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "extraction_method")
