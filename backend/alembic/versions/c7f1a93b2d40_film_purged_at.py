"""record when a deleted film's objects were actually purged

Revision ID: c7f1a93b2d40
Revises: b4c8d02a71e9
Create Date: 2026-09-01 19:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7f1a93b2d40"
down_revision: str | None = "b4c8d02a71e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("films", sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))
    # The purge sweep scans for films whose grace period has lapsed. Without
    # this it is a full table scan of every film ever created, forever.
    op.create_index(
        "ix_films_pending_purge",
        "films",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL AND purged_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_films_pending_purge", table_name="films")
    op.drop_column("films", "purged_at")
