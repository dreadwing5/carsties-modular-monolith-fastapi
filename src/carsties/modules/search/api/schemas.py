"""≈ SearchService's Item model + the anonymous paged result shape."""

from datetime import datetime
from typing import Any

from carsties.shared.schemas import CamelModel


class SearchItemDto(CamelModel):
    id: str
    reserve_price: int = 0
    seller: str | None = None
    winner: str | None = None
    sold_amount: int | None = None
    current_high_bid: int | None = None
    created_at: datetime
    updated_at: datetime
    auction_end: datetime
    status: str | None = None
    make: str | None = None
    model: str | None = None
    color: str | None = None
    year: int | None = None
    mileage: int | None = None
    image_url: str | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> "SearchItemDto":
        data = {key: value for key, value in doc.items() if key not in ("_id", "score")}
        return cls(id=str(doc["_id"]), **data)


class SearchResultDto(CamelModel):
    results: list[SearchItemDto]
    page_count: int
    total_count: int
