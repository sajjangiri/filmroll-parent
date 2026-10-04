"""Database models.

Three tables carry the whole product loop: a film is the event and the tenant,
guests join it without accounts, and shots are the photos.

Two schema choices are load-bearing:

* ``Shot.id`` has no server default. The client generates it before uploading,
  which is what makes the reserve/upload/commit sequence idempotent under the
  retry storms that venue wifi guarantees.
* ``Shot.hidden_at`` exists from the first migration even though the moderation
  UI comes later. Adding it now costs nothing; retrofitting it would mean
  revisiting every gallery, export and recap query.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ShotState(StrEnum):
    RESERVED = "reserved"
    UPLOADED = "uploaded"
    EXPIRED = "expired"


shot_state_enum = SAEnum(
    ShotState,
    name="shot_state",
    values_callable=lambda enum: [member.value for member in enum],
)


class Film(Base):
    __tablename__ = "films"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)

    title: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(40), default="other")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # No new shots accepted after this moment.
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Scheduled develop time.
    reveal_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Set only when the host taps "develop now", which overrides the schedule.
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A live album rather than a disposable camera: shots are visible as they
    # land, so there is no reveal to wait for. Fixed at creation — once guests
    # have seen a photo it cannot be un-seen, so this never becomes scheduled.
    instant_reveal: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    # Shared is the product: one album everyone at the event can see after
    # develop. Private means each guest only sees their own shots; the host
    # inbox and ZIP still hold the whole roll.
    shared_gallery: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

    shot_limit: Mapped[int] = mapped_column(Integer, default=24)
    guest_cap: Mapped[int] = mapped_column(Integer, default=5)
    # What the host has paid for. guest_cap cannot exceed this; raising it is
    # a Stripe Checkout, not a PATCH. The check constraint is the backstop so
    # a missed application check cannot give away a 250-guest wedding.
    entitled_guest_cap: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    keep_forever: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    unlimited_shots: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    # Paid add-on. Without it guests cannot reserve a clip at all.
    video_pack: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Inclusive storage window. The ZIP export stays free after this date; the
    # gallery and originals do not. keep_forever wins over the date.
    storage_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Optional gate on joining. Keyed hash, never the digits themselves, and
    # never returned on any payload — the public film only admits that it exists.
    join_pin_hash: Mapped[str | None] = mapped_column(String(64))

    # Recovery and notifications. Never returned on the public film payload.
    host_email: Mapped[str | None] = mapped_column(String(254))
    reveal_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Set when the host deletes the film. The row survives; the photos do not.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Stamped once the grace period has run out and the bytes are actually gone.
    # After this there is nothing left to restore.
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    guests: Mapped[list[Guest]] = relationship(back_populates="film", cascade="all, delete-orphan")
    shots: Mapped[list[Shot]] = relationship(back_populates="film", cascade="all, delete-orphan")
    payments: Mapped[list[Payment]] = relationship(
        back_populates="film", cascade="all, delete-orphan"
    )
    seats: Mapped[list[FilmSeat]] = relationship(
        back_populates="film", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("shot_limit > 0", name="ck_films_shot_limit_positive"),
        CheckConstraint("guest_cap > 0", name="ck_films_guest_cap_positive"),
        CheckConstraint("entitled_guest_cap > 0", name="ck_films_entitled_positive"),
        CheckConstraint("guest_cap <= entitled_guest_cap", name="ck_films_cap_within_entitlement"),
        # The purge sweep runs against this handful of rows, not every film.
        Index(
            "ix_films_pending_purge",
            "deleted_at",
            postgresql_where=text("deleted_at IS NOT NULL AND purged_at IS NULL"),
        ),
    )


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    film_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("films.id", ondelete="CASCADE"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(80))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    film: Mapped[Film] = relationship(back_populates="guests")
    shots: Mapped[list[Shot]] = relationship(back_populates="guest", cascade="all, delete-orphan")
    push_token: Mapped[GuestPushToken | None] = relationship(
        back_populates="guest", cascade="all, delete-orphan", uselist=False
    )


class GuestPushToken(Base):
    """Where to ping this guest when the film develops.

    The host already gets email. Guests are holding a camera in their pocket,
    so a push is the matching channel. One token per guest: a new phone
    overwrites the old one rather than accumulating a list we would then have
    to prune.
    """

    __tablename__ = "guest_push_tokens"

    guest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guests.id", ondelete="CASCADE"), primary_key=True
    )
    film_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("films.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(200))
    locale: Mapped[str] = mapped_column(String(8), default="en", server_default="en")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    guest: Mapped[Guest] = relationship(back_populates="push_token")

    __table_args__ = (
        CheckConstraint("locale in ('en', 'es', 'fr')", name="ck_guest_push_tokens_locale"),
    )


class Shot(Base):
    __tablename__ = "shots"

    # Supplied by the client, never defaulted here. See module docstring.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)

    film_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("films.id", ondelete="CASCADE"))
    guest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))

    state: Mapped[ShotState] = mapped_column(shot_state_enum, default=ShotState.RESERVED)
    storage_key: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(60), default="image/jpeg")
    # "photo" or "clip". Each kind has its own per-guest allowance.
    kind: Mapped[str] = mapped_column(String(10), default="photo", server_default="photo")
    # Set by the transcode, after trimming. Null for photos.
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # For a clip this also means "transcoded": a clip is never shown before it.
    derivative_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Host moderation. A hidden shot must never appear in a gallery, export or
    # recap, and must never have a signed URL minted for it.
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    film: Mapped[Film] = relationship(back_populates="shots")
    guest: Mapped[Guest] = relationship(back_populates="shots")
    reports: Mapped[list[ShotReport]] = relationship(
        back_populates="shot", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Counting a guest's live shots is the hot path for cap enforcement.
        Index("ix_shots_guest_state", "guest_id", "state"),
        # Gallery reads.
        Index("ix_shots_film_state", "film_id", "state"),
        # The sweeper scans for stale reservations by age.
        Index("ix_shots_state_reserved_at", "state", "reserved_at"),
        CheckConstraint("kind in ('photo', 'clip')", name="ck_shots_kind"),
    )


class ShotReport(Base):
    """A guest flagging a photo for the host's attention.

    A report is a signal, never an action. Nothing here hides a shot: at a party
    with a hundred guests, a handful of friends could otherwise agree to bury a
    photograph the couple actually wanted, and moderation belongs to whoever is
    hosting. What the count buys is the host's attention, which is the scarce
    resource when they are on the dance floor rather than the dashboard.
    """

    __tablename__ = "shot_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    shot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shots.id", ondelete="CASCADE"), index=True
    )
    # Who raised it. Cascades with the guest, and makes one-per-guest enforceable.
    guest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    shot: Mapped[Shot] = relationship(back_populates="reports")

    __table_args__ = (
        # One guest, one vote. Without this a single phone can manufacture a
        # crowd and the count stops meaning anything.
        UniqueConstraint("shot_id", "guest_id", name="uq_shot_reports_shot_guest"),
        CheckConstraint(
            "reason in ('inappropriate', 'private', 'other')", name="ck_shot_reports_reason"
        ),
    )


class Payment(Base):
    """One Checkout session (or fake stand-in) against a film.

    The row is the audit trail and the idempotency key. Stripe will retry a
    webhook; applying the same session twice must not charge the cap twice and
    must not insert a second payment.
    """

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    film_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("films.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20), default="stripe")
    provider_session_id: Mapped[str] = mapped_column(String(255), unique=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(40))
    guest_cap: Mapped[int | None] = mapped_column(Integer)
    # What the catalog quoted, before any tax Stripe adds on top.
    amount_cents: Mapped[int] = mapped_column(Integer)
    # What Stripe actually captured, tax included. Null until the payment lands,
    # and on fake Checkout, where no money moved.
    total_cents: Mapped[int | None] = mapped_column(Integer)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), default="usd")
    status: Mapped[str] = mapped_column(String(20), default="open")
    # Stripe hosts the receipt; storing the URL avoids an API call per view.
    receipt_url: Mapped[str | None] = mapped_column(String(512))
    # The address the receipt went to, which is not necessarily the host email.
    customer_email: Mapped[str | None] = mapped_column(String(254))
    refunded_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    film: Mapped[Film] = relationship(back_populates="payments")


class FilmSeat(Base):
    """A co-host or photographer the owner has let into this film.

    There are still no accounts. A seat is a revocable row that a token points
    at: the JWT carries the seat id, and every request re-reads this row. That
    is what makes "remove the planner" work without waiting a year for a token
    to expire.

    The film creator has no seat. Their token predates this table and stays
    ``role="host"``, which is the one role that can manage seats.
    """

    __tablename__ = "film_seats"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    film_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("films.id", ondelete="CASCADE"), index=True
    )
    # "cohost" (can moderate and reveal) or "photographer" (read and export).
    role: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Stamped the first time an invite is exchanged for a durable token.
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    film: Mapped[Film] = relationship(back_populates="seats")

    __table_args__ = (
        CheckConstraint("role in ('cohost', 'photographer')", name="ck_film_seats_role"),
    )
