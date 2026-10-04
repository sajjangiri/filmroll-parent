"""optional PIN on joining a film

Revision ID: d3a95e17c8b2
Revises: c7f1a93b2d40
Create Date: 2026-09-01 19:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d3a95e17c8b2"
down_revision: str | None = "c7f1a93b2d40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("films", sa.Column("join_pin_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("films", "join_pin_hash")
