"""Mongo persistence for the search read model (≈ MongoDB.Entities calls)."""

import math
from datetime import datetime
from typing import Any

from carsties.modules.search.infrastructure.db import Document, get_items

Sort = list[tuple[str, Any]]


async def save(item: Document) -> None:
    await get_items().replace_one({"_id": item["_id"]}, item, upsert=True)


async def update_fields(item_id: str, fields: Document) -> None:
    result = await get_items().update_one({"_id": item_id}, {"$set": fields})
    if not result.acknowledged:
        raise RuntimeError("Problem updating mongodb")


async def delete(item_id: str) -> None:
    result = await get_items().delete_one({"_id": item_id})
    if not result.acknowledged:
        raise RuntimeError("Problem deleting auction")


async def latest_updated_at() -> datetime | None:
    doc = await get_items().find_one(sort=[("updated_at", -1)], projection=["updated_at"])
    return doc["updated_at"] if doc else None


async def paged_search(
    query_filter: Document, sort: Sort, page_number: int, page_size: int
) -> tuple[list[Document], int, int]:
    """≈ MongoDB.Entities PagedSearch — (results, page_count, total_count)."""
    items = get_items()
    total_count = await items.count_documents(query_filter)

    projection = None
    if "$text" in query_filter:
        projection = {"score": {"$meta": "textScore"}}

    cursor = (
        items.find(query_filter, projection)
        .sort(sort)
        .skip((page_number - 1) * page_size)
        .limit(page_size)
    )
    results = [doc async for doc in cursor]
    page_count = math.ceil(total_count / page_size) if page_size else 0
    return results, page_count, total_count
