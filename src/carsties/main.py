"""≈ Program.cs — builds the app, wires module routers, consumers and hosted
services (outbox poller), and runs the DB initializers.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from carsties.gateway import GatewayMiddleware
from carsties.modules.auctions.api.router import router as auctions_router
from carsties.modules.auctions.application.consumers import (
    register_consumers as register_auctions_consumers,
)
from carsties.modules.auctions.infrastructure import outbox
from carsties.modules.auctions.infrastructure.seed import init_db as init_auctions_db
from carsties.modules.search.api.router import router as search_router
from carsties.modules.search.application.consumers import (
    register_consumers as register_search_consumers,
)
from carsties.modules.search.application.sync import init_db as init_search_db
from carsties.modules.search.infrastructure import db as search_db
from carsties.shared.database import dispose_engine
from carsties.shared.events import event_bus
from carsties.shared.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ≈ MassTransit consumer registration
    register_search_consumers(event_bus)
    register_auctions_consumers(event_bus)

    # ≈ DbInitializer.InitDb in each service's Program.cs
    if get_settings().seed_database:
        try:
            await init_auctions_db()
        except Exception:
            logger.exception("Auctions DB init failed")
        try:
            await init_search_db()
        except Exception:
            logger.exception("Search DB init failed")

    # ≈ the MassTransit outbox delivery service (IHostedService)
    poller = asyncio.create_task(outbox.poll_outbox_forever())

    yield

    poller.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await poller
    await search_db.close()
    await dispose_engine()


app = FastAPI(title="Carsties", lifespan=lifespan)

# ≈ Carsties.GatewayService (YARP): public /auctions and /search routes
app.add_middleware(GatewayMiddleware)

app.include_router(auctions_router)
app.include_router(search_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "healthy"}
