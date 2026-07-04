"""Mongo client setup + the text index the search queries rely on."""

from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection

from carsties.shared.settings import get_settings

Document = dict[str, Any]

_client: AsyncMongoClient[Document] | None = None


def get_client() -> AsyncMongoClient[Document]:
    global _client
    if _client is None:
        _client = AsyncMongoClient(get_settings().mongodb_url)
    return _client


def get_items() -> AsyncCollection[Document]:
    return get_client()[get_settings().mongodb_database]["items"]


async def init_indexes() -> None:
    await get_items().create_index([("make", "text"), ("model", "text"), ("color", "text")])


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
