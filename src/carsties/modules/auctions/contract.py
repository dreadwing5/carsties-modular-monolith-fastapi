"""Public façade of the auctions module — its integration events plus its
public query API. This file is the ONLY thing other modules may import
(enforced by .importlinter). It depends only on the domain layer, so
importing it never drags in another layer.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from carsties.modules.auctions.domain.entities import Auction, Item


class AuctionCreated(BaseModel):
    id: UUID
    reserve_price: int
    seller: str
    winner: str | None = None
    sold_amount: int | None = None
    current_high_bid: int | None = None
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


class AuctionUpdated(BaseModel):
    id: UUID
    updated_at: datetime
    make: str | None = None
    model: str | None = None
    year: int | None = None
    color: str | None = None
    mileage: int | None = None


class AuctionDeleted(BaseModel):
    id: UUID


def to_auction_created(auction: Auction) -> AuctionCreated:
    return AuctionCreated(
        id=auction.id,
        reserve_price=auction.reserve_price,
        seller=auction.seller,
        winner=auction.winner,
        sold_amount=auction.sold_amount,
        current_high_bid=auction.current_high_bid,
        created_at=auction.created_at,
        updated_at=auction.updated_at,
        auction_end=auction.auction_end,
        status=auction.status.value,
        make=auction.item.make,
        model=auction.item.model,
        color=auction.item.color,
        year=auction.item.year,
        mileage=auction.item.mileage,
        image_url=auction.item.image_url,
    )


async def get_auctions(
    session: AsyncSession, since: datetime | None = None
) -> list[AuctionCreated]:
    """Public query — lets the search module sync its read model. Between
    separate services this would be an HTTP call; in the monolith it is a
    direct call through the contract, which is fine for reads.
    """
    query = select(Auction).join(Auction.item).order_by(Item.make)
    if since is not None:
        query = query.where(Auction.updated_at > since)
    auctions = (await session.execute(query)).unique().scalars().all()
    return [to_auction_created(auction) for auction in auctions]
