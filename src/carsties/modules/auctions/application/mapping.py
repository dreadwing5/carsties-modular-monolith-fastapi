"""Entity → integration event mapping.

Entity → AuctionCreated lives in contract.py (the snapshot query needs it too);
this module adds the write-side mappings used by the service.
"""

from carsties.modules.auctions.contract import (
    AuctionUpdated,
    to_auction_created,
)
from carsties.modules.auctions.domain.entities import Auction

__all__ = ["to_auction_created", "to_auction_updated"]


def to_auction_updated(auction: Auction) -> AuctionUpdated:
    return AuctionUpdated(
        id=auction.id,
        updated_at=auction.updated_at,
        make=auction.item.make,
        model=auction.item.model,
        color=auction.item.color,
        year=auction.item.year,
        mileage=auction.item.mileage,
    )
