"""entitlements and payments

Revision ID: 8c4e2a91b7d3
Revises: 154b14bc3840
Create Date: 2026-08-18 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8c4e2a91b7d3"
down_revision: str | None = "154b14bc3840"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "films",
        sa.Column("entitled_guest_cap", sa.Integer(), server_default="5", nullable=False),
    )
    op.add_column(
        "films",
        sa.Column("keep_forever", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("films", sa.Column("storage_until", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE films SET storage_until = created_at + interval '365 days'")
    # Existing films were created before billing; honour the cap they already have.
    op.execute("UPDATE films SET entitled_guest_cap = GREATEST(guest_cap, 5)")
    op.alter_column("films", "storage_until", nullable=False)
    op.create_check_constraint("ck_films_entitled_positive", "films", "entitled_guest_cap > 0")
    op.create_check_constraint(
        "ck_films_cap_within_entitlement", "films", "guest_cap <= entitled_guest_cap"
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("film_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_session_id", sa.String(length=255), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("guest_cap", sa.Integer(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="open", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["film_id"], ["films.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_session_id"),
    )
    op.create_index(op.f("ix_payments_film_id"), "payments", ["film_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_film_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_constraint("ck_films_cap_within_entitlement", "films", type_="check")
    op.drop_constraint("ck_films_entitled_positive", "films", type_="check")
    op.drop_column("films", "storage_until")
    op.drop_column("films", "keep_forever")
    op.drop_column("films", "entitled_guest_cap")
