"""≈ Carsties.AuctionService.Data.DbInitializer — migrate, then seed the same
ten auctions (same GUIDs) the .NET service ships with.
"""

import asyncio
import logging
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from carsties.modules.auctions.domain.entities import Auction, Item, Status, utcnow
from carsties.shared.database import get_session_factory

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[5]


def _migrate() -> None:
    """≈ context.Database.Migrate()."""
    config = Config(PROJECT_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    command.upgrade(config, "head")


def _seed_auctions() -> list[Auction]:
    def auction(
        auction_id: str,
        *,
        seller: str,
        status: Status = Status.LIVE,
        reserve_price: int = 0,
        end_in_days: int,
        make: str,
        model: str,
        color: str,
        mileage: int,
        year: int,
        image_url: str,
    ) -> Auction:
        return Auction(
            id=UUID(auction_id),
            status=status,
            reserve_price=reserve_price,
            seller=seller,
            auction_end=utcnow() + timedelta(days=end_in_days),
            item=Item(
                make=make, model=model, color=color, mileage=mileage, year=year,
                image_url=image_url,
            ),
        )

    cdn = "https://cdn.pixabay.com/photo"
    return [
        auction(
            "afbee524-5972-4075-8800-7d1f9d7b0a0c", seller="bob", reserve_price=20000,
            end_in_days=10, make="Ford", model="GT", color="White", mileage=50000,
            year=2020, image_url=f"{cdn}/2016/05/06/16/32/car-1376190_960_720.jpg",
        ),
        auction(
            "c8c3ec17-01bf-49db-82aa-1ef80b833a9f", seller="alice", reserve_price=90000,
            end_in_days=60, make="Bugatti", model="Veyron", color="Black", mileage=15035,
            year=2018, image_url=f"{cdn}/2012/05/29/00/43/car-49278_960_720.jpg",
        ),
        auction(
            "bbab4d5a-8565-48b1-9450-5ac2a5c4a654", seller="bob",
            end_in_days=4, make="Ford", model="Mustang", color="Black", mileage=65125,
            year=2023, image_url=f"{cdn}/2012/11/02/13/02/car-63930_960_720.jpg",
        ),
        auction(
            "155225c1-4448-4066-9886-6786536e05ea", seller="tom", reserve_price=50000,
            status=Status.RESERVE_NOT_MET, end_in_days=-10, make="Mercedes", model="SLK",
            color="Silver", mileage=15001, year=2020,
            image_url=f"{cdn}/2016/04/17/22/10/mercedes-benz-1335674_960_720.png",
        ),
        auction(
            "466e4744-4dc5-4987-aae0-b621acfc5e39", seller="alice", reserve_price=20000,
            end_in_days=30, make="BMW", model="X1", color="White", mileage=90000,
            year=2017, image_url=f"{cdn}/2017/08/31/05/47/bmw-2699538_960_720.jpg",
        ),
        auction(
            "dc1e4071-d19d-459b-b848-b5c3cd3d151f", seller="bob", reserve_price=20000,
            end_in_days=45, make="Ferrari", model="Spider", color="Red", mileage=50000,
            year=2015, image_url=f"{cdn}/2017/11/09/01/49/ferrari-458-spider-2932191_960_720.jpg",
        ),
        auction(
            "47111973-d176-4feb-848d-0ea22641c31a", seller="alice", reserve_price=150000,
            end_in_days=13, make="Ferrari", model="F-430", color="Red", mileage=5000,
            year=2022, image_url=f"{cdn}/2017/11/08/14/39/ferrari-f430-2930661_960_720.jpg",
        ),
        auction(
            "6a5011a1-fe1f-47df-9a32-b5346b289391", seller="bob",
            end_in_days=19, make="Audi", model="R8", color="White", mileage=10050,
            year=2021, image_url=f"{cdn}/2019/12/26/20/50/audi-r8-4721217_960_720.jpg",
        ),
        auction(
            "40490065-dac7-46b6-acc4-df507e0d6570", seller="tom", reserve_price=20000,
            end_in_days=20, make="Audi", model="TT", color="Black", mileage=25400,
            year=2020, image_url=f"{cdn}/2016/09/01/15/06/audi-1636320_960_720.jpg",
        ),
        auction(
            "3659ac24-29dd-407a-81f5-ecfe6f924b9b", seller="bob", reserve_price=20000,
            end_in_days=48, make="Ford", model="Model T", color="Rust", mileage=150150,
            year=1938, image_url=f"{cdn}/2017/08/02/19/47/vintage-2573090_960_720.jpg",
        ),
    ]


async def init_db() -> None:
    # alembic's command API is sync; run it off the event loop
    await asyncio.to_thread(_migrate)

    async with get_session_factory()() as session:
        existing = (await session.execute(select(Auction.id).limit(1))).first()
        if existing is not None:
            logger.info("Already have data - no need to seed")
            return
        session.add_all(_seed_auctions())
        await session.commit()
        logger.info("Seeded auctions data")
