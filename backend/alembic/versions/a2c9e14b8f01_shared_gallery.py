"""private vs shared gallery visibility

Revision ID: a2c9e14b8f01
Revises: f0d4a2e91b76
Create Date: 2026-09-02 15:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a2c9e14b8f01"
down_revision: str | None = "f0d4a2e91b76"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "films",
        sa.Column(
            "shared_gallery",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("films", "shared_gallery")
