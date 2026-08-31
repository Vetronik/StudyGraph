"""add chunk page number

Revision ID: 0006_add_chunk_page_number
Revises: 0005_add_full_text_search_indexes
Create Date: 2026-08-31 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_add_chunk_page_number"
down_revision: str | None = "0005_add_full_text_search_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column(
            "page_number",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "page_number")
