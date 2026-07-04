"""Fault consumer — reacts to AuctionCreated events whose handlers failed."""

import logging

from carsties.modules.auctions.contract import AuctionCreated
from carsties.shared.events import EventBus, Fault, event_bus

logger = logging.getLogger(__name__)


async def on_auction_created_fault(fault: Fault) -> None:
    logger.info("--> Consuming faulty creation")

    # NOTE: This is just an example of how to handle faults. In a real
    # application, you would want to send log information to a logging service
    # or update an error dashboard.
    if isinstance(fault.exception, ValueError):
        fault.message.model = "FooBar"
        await event_bus.publish(fault.message)
    else:
        logger.info("Not a value error - update error dashboard somewhere")


def register_consumers(bus: EventBus) -> None:
    bus.subscribe_fault(AuctionCreated, on_auction_created_fault)
