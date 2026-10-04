"""payment receipts, tax, refunds

Revision ID: a1e6b30f5c74
Revises: 9d7f1c2e4b08
Create Date: 2026-09-01 18:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1e6b30f5c74"
down_revision: str | None = "9d7f1c2e4b08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("total_cents", sa.Integer(), nullable=True))
    op.add_column(
        "payments",
        sa.Column("tax_cents", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("payments", sa.Column("receipt_url", sa.String(length=512), nullable=True))
    op.add_column("payments", sa.Column("customer_email", sa.String(length=254), nullable=True))
    op.add_column(
        "payments",
        sa.Column("refunded_cents", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "payments", sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Rows that predate tax collection were charged exactly what we quoted.
    op.execute("UPDATE payments SET total_cents = amount_cents WHERE status != 'open'")


def downgrade() -> None:
    op.drop_column("payments", "refunded_at")
    op.drop_column("payments", "refunded_cents")
    op.drop_column("payments", "customer_email")
    op.drop_column("payments", "receipt_url")
    op.drop_column("payments", "tax_cents")
    op.drop_column("payments", "total_cents")
