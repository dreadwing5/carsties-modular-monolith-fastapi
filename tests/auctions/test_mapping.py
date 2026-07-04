from datetime import UTC, datetime
from uuid import UUID

from carsties.modules.auctions.application.mapping import (
    to_auction_created,
    to_auction_updated,
)
from carsties.modules.auctions.domain.entities import Auction, Item, Status

AUCTION_ID = UUID("afbee524-5972-4075-8800-7d1f9d7b0a0c")
NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def make_auction() -> Auction:
    return Auction(
        id=AUCTION_ID,
        reserve_price=20000,
        seller="bob",
        winner=None,
        sold_amount=None,
        current_high_bid=None,
        created_at=NOW,
        updated_at=NOW,
        auction_end=NOW,
        status=Status.LIVE,
        item=Item(
            make="Ford", model="GT", color="White", year=2020, mileage=50000,
            image_url="http://example.com/car.jpg",
        ),
    )


def test_to_auction_created_flattens_item_and_stringifies_status():
    event = to_auction_created(make_auction())

    assert event.id == AUCTION_ID
    assert event.status == "Live"
    assert event.make == "Ford"
    assert event.model == "GT"
    assert event.reserve_price == 20000
    assert event.seller == "bob"


def test_to_auction_updated_carries_only_item_fields():
    event = to_auction_updated(make_auction())

    assert event.id == AUCTION_ID
    assert event.updated_at == NOW
    assert event.make == "Ford"
    assert event.mileage == 50000
    assert not hasattr(event, "seller")
