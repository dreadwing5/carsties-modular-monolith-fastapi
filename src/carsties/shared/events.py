"""In-process event bus (pub/sub between modules).

Modules publish integration events (defined in their contract.py) and other
modules subscribe. Handlers are the same shape they would be as RabbitMQ
consumers, so extracting a module to a microservice later means swapping this
bus for a real broker (e.g. FastStream) without touching the handlers.

Failure semantics:
- a subscription may declare retries
- when a handler still fails, a Fault[event] is published, which other
  handlers may consume (see auctions' fault consumer).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Awaitable[None]]


@dataclass
class Fault:
    """Wraps a message that failed all retries, together with its exception."""

    message: Any
    exception: Exception


@dataclass
class _Subscription:
    handler: Handler
    retries: int
    retry_delay: float


@dataclass
class EventBus:
    _subscriptions: dict[type, list[_Subscription]] = field(default_factory=dict)

    def subscribe(
        self,
        event_type: type,
        handler: Handler,
        *,
        retries: int = 0,
        retry_delay: float = 0.0,
    ) -> None:
        self._subscriptions.setdefault(event_type, []).append(
            _Subscription(handler, retries, retry_delay)
        )

    def subscribe_fault(self, message_type: type, handler: Handler) -> None:
        """Subscribe to Fault events whose failed message is of message_type."""

        async def filtered(fault: Fault) -> None:
            if isinstance(fault.message, message_type):
                await handler(fault)

        self.subscribe(Fault, filtered)

    async def publish(self, event: Any) -> None:
        subscriptions = self._subscriptions.get(type(event), [])
        if not subscriptions and not isinstance(event, Fault):
            logger.debug("No consumers for %s", type(event).__name__)
        for subscription in subscriptions:
            await self._dispatch(subscription, event)

    async def _dispatch(self, subscription: _Subscription, event: Any) -> None:
        for attempt in range(subscription.retries + 1):
            try:
                await subscription.handler(event)
                return
            except Exception as exc:
                if attempt < subscription.retries:
                    logger.warning(
                        "Handler for %s failed (attempt %d/%d), retrying in %.0fs: %s",
                        type(event).__name__,
                        attempt + 1,
                        subscription.retries + 1,
                        subscription.retry_delay,
                        exc,
                    )
                    await asyncio.sleep(subscription.retry_delay)
                    continue
                logger.exception("Handler for %s faulted", type(event).__name__)
                if not isinstance(event, Fault):
                    await self.publish(Fault(message=event, exception=exc))
                return


event_bus = EventBus()
