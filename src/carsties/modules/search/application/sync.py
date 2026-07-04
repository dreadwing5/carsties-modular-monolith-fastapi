"""≈ Carsties.SearchService's DbInitializer + AuctionSvcHttpClient.

On startup the read model catches up on anything it missed: it asks the
auctions module for every auction updated since the newest item it holds. In
the microservices version this was an HTTP call with a Polly retry-forever
policy; in the monolith it is a direct call through the auctions contract.
"""

import logging

from carsties.modules.auctions import contract as auctions
from carsties.modules.search.application.mapping import item_from_created
from carsties.modules.search.infrastructure import db, repository
from carsties.shared.database import get_session_factory

logger = logging.getLogger(__name__)


async def init_db() -> None:
    await db.init_indexes()

    last_updated = await repository.latest_updated_at()

    async with get_session_factory()() as session:
        events = await auctions.get_auctions(session, since=last_updated)

    logger.info("%d returned from the auction service", len(events))

    for event in events:
        await repository.save(item_from_created(event))
