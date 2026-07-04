"""Business logic of the auctions endpoints, extracted to the application
layer. Integration events go through the outbox in the same transaction as
the business change.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from carsties.modules.auctions.application.commands import (
    CreateAuctionCommand,
    UpdateAuctionCommand,
)
from carsties.modules.auctions.application.mapping import (
    to_auction_created,
    to_auction_updated,
)
from carsties.modules.auctions.contract import AuctionDeleted
from carsties.modules.auctions.domain.entities import Auction, Item, Status, utcnow
from carsties.modules.auctions.infrastructure import outbox


class AuctionNotFoundError(Exception):
    pass


class NotAuctionSellerError(Exception):
    pass


def as_utc(value: datetime) -> datetime:
    """Normalize to UTC — naive datetimes are treated as already-UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def get_all(session: AsyncSession, since: datetime | None = None) -> list[Auction]:
    query = select(Auction).join(Auction.item).order_by(Item.make)
    if since is not None:
        query = query.where(Auction.updated_at > as_utc(since))
    return list((await session.execute(query)).unique().scalars().all())


async def get_by_id(session: AsyncSession, auction_id: UUID) -> Auction | None:
    return await session.get(Auction, auction_id)


async def create(session: AsyncSession, command: CreateAuctionCommand, seller: str) -> Auction:
    auction = Auction(
        reserve_price=command.reserve_price,
        auction_end=as_utc(command.auction_end),
        status=Status.LIVE,
        seller=seller,
        item=Item(
            make=command.make,
            model=command.model,
            color=command.color,
            year=command.year,
            mileage=command.mileage,
            image_url=command.image_url,
        ),
    )
    session.add(auction)
    await session.flush()  # populate defaults (id, created_at, ...)

    outbox.enqueue(session, to_auction_created(auction))
    await session.commit()
    return auction


async def update(
    session: AsyncSession, auction_id: UUID, command: UpdateAuctionCommand, username: str
) -> Auction:
    auction = await get_by_id(session, auction_id)
    if auction is None:
        raise AuctionNotFoundError
    if auction.seller != username:
        raise NotAuctionSellerError

    item = auction.item
    item.make = command.make or item.make
    item.model = command.model or item.model
    item.color = command.color or item.color
    item.year = command.year or item.year
    item.mileage = command.mileage or item.mileage
    auction.updated_at = utcnow()

    outbox.enqueue(session, to_auction_updated(auction))
    await session.commit()
    return auction


async def delete(session: AsyncSession, auction_id: UUID, username: str) -> None:
    auction = await get_by_id(session, auction_id)
    if auction is None:
        raise AuctionNotFoundError
    if auction.seller != username:
        raise NotAuctionSellerError

    await session.delete(auction)
    outbox.enqueue(session, AuctionDeleted(id=auction_id))
    await session.commit()
