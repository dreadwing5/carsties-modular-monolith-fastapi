"""≈ Carsties.SearchService.Consumers — the same three consumers, subscribed to
the in-process event bus instead of RabbitMQ endpoints.
"""

import logging

from carsties.modules.auctions.contract import (
    AuctionCreated,
    AuctionDeleted,
    AuctionUpdated,
)
from carsties.modules.search.application.mapping import (
    fields_from_updated,
    item_from_created,
)
from carsties.modules.search.infrastructure import repository
from carsties.shared.events import EventBus

logger = logging.getLogger(__name__)


async def on_auction_created(event: AuctionCreated) -> None:
    item = item_from_created(event)

    # if item["model"] == "Foo":
    #     raise ValueError("Cannot sell cars with the name of Foo")
    # NOTE: This is for demonstration purposes only, to show how failures are
    # handled — the fault ends up in auctions' AuctionCreated fault consumer.

    await repository.save(item)


async def on_auction_updated(event: AuctionUpdated) -> None:
    logger.info("Received AuctionUpdated event for auction with ID: %s", event.id)
    await repository.update_fields(str(event.id), fields_from_updated(event))


async def on_auction_deleted(event: AuctionDeleted) -> None:
    logger.info("Received AuctionDeleted event for auction with ID: %s", event.id)
    await repository.delete(str(event.id))


def register_consumers(bus: EventBus) -> None:
    # ≈ the search-auction-created endpoint's UseMessageRetry(5 x 5s)
    bus.subscribe(AuctionCreated, on_auction_created, retries=5, retry_delay=5.0)
    bus.subscribe(AuctionUpdated, on_auction_updated)
    bus.subscribe(AuctionDeleted, on_auction_deleted)
