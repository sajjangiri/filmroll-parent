"""co-host and photographer seats

Revision ID: b4c8d02a71e9
Revises: a1e6b30f5c74
Create Date: 2026-09-01 18:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4c8d02a71e9"
down_revision: str | None = "a1e6b30f5c74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "film_seats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("film_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["film_id"], ["films.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("role in ('cohost', 'photographer')", name="ck_film_seats_role"),
    )
    op.create_index("ix_film_seats_film_id", "film_seats", ["film_id"])


def downgrade() -> None:
    op.drop_index("ix_film_seats_film_id", table_name="film_seats")
    op.drop_table("film_seats")
