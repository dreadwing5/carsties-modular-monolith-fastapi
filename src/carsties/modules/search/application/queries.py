"""Search query construction — the pure-logic core of the search endpoint.

Kept free of Mongo I/O so the sort/filter behavior is unit testable.
"""

from datetime import datetime, timedelta
from typing import Any

Sort = list[tuple[str, Any]]

MAX_PAGE_SIZE = 50
DEFAULT_PAGE_SIZE = 4


def build_search(
    *,
    search_term: str | None,
    order_by: str | None,
    filter_by: str | None,
    seller: str | None,
    winner: str | None,
    now: datetime,
) -> tuple[dict[str, Any], Sort]:
    query_filter: dict[str, Any] = {}
    sort: Sort = []

    if search_term:
        query_filter["$text"] = {"$search": search_term}
        sort.append(("score", {"$meta": "textScore"}))  # best text match first

    match order_by:
        case "make":
            sort += [("make", 1), ("model", 1)]
        case "new":
            sort.append(("created_at", -1))
        case _:
            sort.append(("auction_end", 1))

    match filter_by:
        case "finished":
            query_filter["auction_end"] = {"$lt": now}
        case "endingSoon":
            query_filter["auction_end"] = {"$lt": now + timedelta(hours=6), "$gt": now}
        case _:
            query_filter["auction_end"] = {"$gt": now}

    if seller:
        query_filter["seller"] = seller
    if winner:
        query_filter["winner"] = winner

    return query_filter, sort


def clamp_paging(page_number: int | None, page_size: int | None) -> tuple[int, int]:
    return page_number or 1, min(page_size or DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE)
