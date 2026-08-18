"""host email, unlimited shots, notification stamps

Revision ID: 9d7f1c2e4b08
Revises: 8c4e2a91b7d3
Create Date: 2026-08-18 17:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9d7f1c2e4b08"
down_revision: str | None = "8c4e2a91b7d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "films",
        sa.Column("unlimited_shots", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("films", sa.Column("host_email", sa.String(length=254), nullable=True))
    op.add_column(
        "films", sa.Column("reveal_notified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "films", sa.Column("retention_notified_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("films", "retention_notified_at")
    op.drop_column("films", "reveal_notified_at")
    op.drop_column("films", "host_email")
    op.drop_column("films", "unlimited_shots")
