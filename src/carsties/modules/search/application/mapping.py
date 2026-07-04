"""Integration events → search read-model documents."""

from typing import Any

from carsties.modules.auctions.contract import AuctionCreated, AuctionUpdated


def item_from_created(event: AuctionCreated) -> dict[str, Any]:
    return {
        "_id": str(event.id),
        "reserve_price": event.reserve_price,
        "seller": event.seller,
        "winner": event.winner or "",
        "sold_amount": event.sold_amount,
        "current_high_bid": event.current_high_bid,
        "created_at": event.created_at,
        "updated_at": event.updated_at,
        "auction_end": event.auction_end,
        "status": event.status,
        "make": event.make,
        "model": event.model,
        "color": event.color,
        "year": event.year,
        "mileage": event.mileage,
        "image_url": event.image_url,
    }


def fields_from_updated(event: AuctionUpdated) -> dict[str, Any]:
    """Only the item fields an update may change — never price/status."""
    return {
        "make": event.make,
        "model": event.model,
        "color": event.color,
        "year": event.year,
        "mileage": event.mileage,
        "updated_at": event.updated_at,
    }
