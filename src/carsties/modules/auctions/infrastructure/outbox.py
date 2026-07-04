"""Transactional outbox.

Integration events are written to an outbox table inside the same transaction
as the business change; a background poller then publishes them to the event
bus. If the process dies between commit and publish, the event is picked up on
the next poll — at-least-once delivery.
"""

import asyncio
import logging
import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from carsties.modules.auctions import contract
from carsties.modules.auctions.domain.entities import SCHEMA, utcnow
from carsties.shared.database import Base, get_session_factory
from carsties.shared.events import event_bus
from carsties.shared.settings import get_settings

logger = logging.getLogger(__name__)

_EVENT_TYPES: dict[str, type[BaseModel]] = {
    t.__name__: t
    for t in (contract.AuctionCreated, contract.AuctionUpdated, contract.AuctionDeleted)
}


class OutboxMessage(Base):
    __tablename__ = "outbox"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


def enqueue(session: AsyncSession, event: BaseModel) -> None:
    """Stage an event for publication inside the caller's transaction."""
    session.add(
        OutboxMessage(event_type=type(event).__name__, payload=event.model_dump_json())
    )


async def process_outbox_once() -> int:
    async with get_session_factory()() as session:
        messages = (
            (
                await session.execute(
                    select(OutboxMessage)
                    .where(OutboxMessage.processed_at.is_(None))
                    .order_by(OutboxMessage.created_at)
                )
            )
            .scalars()
            .all()
        )
        for message in messages:
            event = _EVENT_TYPES[message.event_type].model_validate_json(message.payload)
            await event_bus.publish(event)
            message.processed_at = utcnow()
            await session.commit()
        return len(messages)


async def poll_outbox_forever() -> None:
    interval = get_settings().outbox_poll_interval_seconds
    logger.info("Outbox poller started (every %.0fs)", interval)
    while True:
        try:
            await process_outbox_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Outbox poll failed")
        await asyncio.sleep(interval)
