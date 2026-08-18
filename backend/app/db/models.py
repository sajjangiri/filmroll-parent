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
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
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

    shot_limit: Mapped[int] = mapped_column(Integer, default=24)
    guest_cap: Mapped[int] = mapped_column(Integer, default=25)

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    guests: Mapped[list[Guest]] = relationship(back_populates="film", cascade="all, delete-orphan")
    shots: Mapped[list[Shot]] = relationship(back_populates="film", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("shot_limit > 0", name="ck_films_shot_limit_positive"),
        CheckConstraint("guest_cap > 0", name="ck_films_guest_cap_positive"),
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


class Shot(Base):
    __tablename__ = "shots"

    # Supplied by the client, never defaulted here. See module docstring.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)

    film_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("films.id", ondelete="CASCADE"))
    guest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))

    state: Mapped[ShotState] = mapped_column(shot_state_enum, default=ShotState.RESERVED)
    storage_key: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(60), default="image/jpeg")

    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    derivative_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Host moderation. A hidden shot must never appear in a gallery, export or
    # recap, and must never have a signed URL minted for it.
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    film: Mapped[Film] = relationship(back_populates="shots")
    guest: Mapped[Guest] = relationship(back_populates="shots")

    __table_args__ = (
        # Counting a guest's live shots is the hot path for cap enforcement.
        Index("ix_shots_guest_state", "guest_id", "state"),
        # Gallery reads.
        Index("ix_shots_film_state", "film_id", "state"),
        # The sweeper scans for stale reservations by age.
        Index("ix_shots_state_reserved_at", "state", "reserved_at"),
    )
