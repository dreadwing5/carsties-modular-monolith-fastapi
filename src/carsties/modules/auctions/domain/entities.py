"""Auctions domain model — Auction, Item, Status.

Tables live in the "auctions" Postgres schema: one database, one schema per
module, so no other module can join across these tables.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from carsties.shared.database import Base

SCHEMA = "auctions"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Status(enum.Enum):
    LIVE = "Live"
    FINISHED = "Finished"
    RESERVE_NOT_MET = "ReserveNotMet"


class Auction(Base):
    __tablename__ = "auctions"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reserve_price: Mapped[int] = mapped_column(default=0)
    seller: Mapped[str] = mapped_column(String)
    winner: Mapped[str | None] = mapped_column(String, default=None)
    sold_amount: Mapped[int | None] = mapped_column(default=None)
    current_high_bid: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    auction_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[Status] = mapped_column(
        Enum(Status, values_callable=lambda s: [e.value for e in s], schema=SCHEMA),
        default=Status.LIVE,
    )

    item: Mapped["Item"] = relationship(
        back_populates="auction", cascade="all, delete-orphan", lazy="joined"
    )


class Item(Base):
    __tablename__ = "items"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    make: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    color: Mapped[str] = mapped_column(String)
    year: Mapped[int]
    mileage: Mapped[int]
    image_url: Mapped[str] = mapped_column(String)

    auction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.auctions.id", ondelete="CASCADE"), unique=True
    )
    auction: Mapped[Auction] = relationship(back_populates="item")
