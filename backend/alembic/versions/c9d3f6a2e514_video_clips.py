"""video pack add-on and guest clips

Revision ID: c9d3f6a2e514
Revises: b8e4f17c9a20
Create Date: 2026-09-27 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d3f6a2e514"
down_revision: str | None = "b8e4f17c9a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "films",
        sa.Column("video_pack", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "shots",
        sa.Column("kind", sa.String(length=10), server_default="photo", nullable=False),
    )
    op.add_column("shots", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_shots_kind", "shots", "kind in ('photo', 'clip')")


def downgrade() -> None:
    op.drop_constraint("ck_shots_kind", "shots", type_="check")
    op.drop_column("shots", "duration_ms")
    op.drop_column("shots", "kind")
    op.drop_column("films", "video_pack")
