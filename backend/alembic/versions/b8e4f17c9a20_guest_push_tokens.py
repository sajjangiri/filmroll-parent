"""guest expo push tokens for reveal notices

Revision ID: b8e4f17c9a20
Revises: a2c9e14b8f01
Create Date: 2026-09-02 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8e4f17c9a20"
down_revision: str | None = "a2c9e14b8f01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "guest_push_tokens",
        sa.Column("guest_id", sa.Uuid(), nullable=False),
        sa.Column("film_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(length=200), nullable=False),
        sa.Column("locale", sa.String(length=8), server_default="en", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("locale in ('en', 'es', 'fr')", name="ck_guest_push_tokens_locale"),
        sa.ForeignKeyConstraint(["film_id"], ["films.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("guest_id"),
    )
    op.create_index("ix_guest_push_tokens_film_id", "guest_push_tokens", ["film_id"])


def downgrade() -> None:
    op.drop_index("ix_guest_push_tokens_film_id", table_name="guest_push_tokens")
    op.drop_table("guest_push_tokens")
