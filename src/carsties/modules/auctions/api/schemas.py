"""≈ Carsties.AuctionService.DTOs — Pydantic replaces DTO classes,
FluentValidation and AutoMapper. camelCase aliases keep the wire format
identical to the .NET JSON output.
"""

from datetime import datetime
from uuid import UUID

from carsties.shared.schemas import CamelModel


class AuctionDto(CamelModel):
    id: UUID
    reserve_price: int
    seller: str
    winner: str | None
    sold_amount: int | None
    current_high_bid: int | None
    created_at: datetime
    updated_at: datetime
    auction_end: datetime
    status: str
    make: str
    model: str
    color: str
    year: int
    mileage: int
    image_url: str


class CreateAuctionDto(CamelModel):
    make: str
    model: str
    color: str
    year: int
    mileage: int
    image_url: str
    reserve_price: int
    auction_end: datetime


class UpdateAuctionDto(CamelModel):
    make: str | None = None
    model: str | None = None
    year: int | None = None
    color: str | None = None
    mileage: int | None = None
