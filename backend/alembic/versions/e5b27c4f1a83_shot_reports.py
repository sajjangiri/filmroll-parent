"""guests can report a photo to the host

Revision ID: e5b27c4f1a83
Revises: d3a95e17c8b2
Create Date: 2026-09-01 19:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5b27c4f1a83"
down_revision: str | None = "d3a95e17c8b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shot_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shot_id", sa.Uuid(), nullable=False),
        sa.Column("guest_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["shot_id"], ["shots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # One guest, one vote, so a single phone cannot manufacture a crowd.
        sa.UniqueConstraint("shot_id", "guest_id", name="uq_shot_reports_shot_guest"),
        sa.CheckConstraint(
            "reason in ('inappropriate', 'private', 'other')", name="ck_shot_reports_reason"
        ),
    )
    op.create_index("ix_shot_reports_shot_id", "shot_reports", ["shot_id"])


def downgrade() -> None:
    op.drop_index("ix_shot_reports_shot_id", table_name="shot_reports")
    op.drop_table("shot_reports")
