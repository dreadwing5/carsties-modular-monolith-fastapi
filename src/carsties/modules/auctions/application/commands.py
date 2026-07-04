"""Application-layer commands (≈ the write-side DTOs handed to MediatR)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CreateAuctionCommand:
    make: str
    model: str
    color: str
    year: int
    mileage: int
    image_url: str
    reserve_price: int
    auction_end: datetime


@dataclass(frozen=True)
class UpdateAuctionCommand:
    make: str | None = None
    model: str | None = None
    year: int | None = None
    color: str | None = None
    mileage: int | None = None
