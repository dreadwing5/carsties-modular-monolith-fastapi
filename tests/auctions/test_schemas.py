"""Wire-format parity: the JSON shapes must match the .NET camelCase DTOs."""

from datetime import UTC, datetime
from uuid import UUID

from carsties.modules.auctions.api.schemas import AuctionDto, CreateAuctionDto, UpdateAuctionDto

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_create_dto_accepts_camel_case_payload():
    dto = CreateAuctionDto.model_validate(
        {
            "make": "Ford",
            "model": "GT",
            "color": "White",
            "year": 2020,
            "mileage": 50000,
            "imageUrl": "http://example.com/car.jpg",
            "reservePrice": 20000,
            "auctionEnd": "2026-08-01T00:00:00Z",
        }
    )
    assert dto.image_url == "http://example.com/car.jpg"
    assert dto.reserve_price == 20000


def test_update_dto_fields_are_all_optional():
    dto = UpdateAuctionDto.model_validate({})
    assert dto.make is None
    assert dto.mileage is None


def test_auction_dto_serializes_camel_case():
    dto = AuctionDto(
        id=UUID("afbee524-5972-4075-8800-7d1f9d7b0a0c"),
        reserve_price=20000,
        seller="bob",
        winner=None,
        sold_amount=None,
        current_high_bid=None,
        created_at=NOW,
        updated_at=NOW,
        auction_end=NOW,
        status="Live",
        make="Ford",
        model="GT",
        color="White",
        year=2020,
        mileage=50000,
        image_url="http://example.com/car.jpg",
    )
    payload = dto.model_dump(by_alias=True)
    assert payload["reservePrice"] == 20000
    assert payload["imageUrl"] == "http://example.com/car.jpg"
    assert payload["currentHighBid"] is None
    assert "reserve_price" not in payload
