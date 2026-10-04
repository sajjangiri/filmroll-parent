"""instant reveal films (live gallery)

Revision ID: f0d4a2e91b76
Revises: e5b27c4f1a83
Create Date: 2026-09-01 20:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f0d4a2e91b76"
down_revision: str | None = "e5b27c4f1a83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "films",
        sa.Column(
            "instant_reveal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("films", "instant_reveal")
