"""HTTP endpoints of the auctions module."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from carsties.modules.auctions.api.schemas import (
    AuctionDto,
    CreateAuctionDto,
    UpdateAuctionDto,
)
from carsties.modules.auctions.application import service
from carsties.modules.auctions.application.commands import (
    CreateAuctionCommand,
    UpdateAuctionCommand,
)
from carsties.modules.auctions.contract import to_auction_created
from carsties.modules.auctions.domain.entities import Auction
from carsties.shared.auth import CurrentUsername
from carsties.shared.database import get_session

router = APIRouter(prefix="/api/auctions", tags=["auctions"])

Session = Annotated[AsyncSession, Depends(get_session)]


def to_dto(auction: Auction) -> AuctionDto:
    return AuctionDto(**to_auction_created(auction).model_dump())


@router.get("", response_model=list[AuctionDto], response_model_by_alias=True)
async def get_all_auctions(session: Session, date: datetime | None = None) -> list[AuctionDto]:
    auctions = await service.get_all(session, since=date)
    return [to_dto(auction) for auction in auctions]


@router.get("/{auction_id}", response_model=AuctionDto, response_model_by_alias=True)
async def get_auction_by_id(session: Session, auction_id: UUID) -> AuctionDto:
    auction = await service.get_by_id(session, auction_id)
    if auction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return to_dto(auction)


@router.post(
    "",
    response_model=AuctionDto,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_auction(
    session: Session,
    username: CurrentUsername,
    dto: CreateAuctionDto,
    request: Request,
    response: Response,
) -> AuctionDto:
    auction = await service.create(
        session, CreateAuctionCommand(**dto.model_dump()), seller=username
    )
    response.headers["Location"] = str(
        request.url_for("get_auction_by_id", auction_id=auction.id)
    )
    return to_dto(auction)


@router.put("/{auction_id}")
async def update_auction(
    session: Session, username: CurrentUsername, auction_id: UUID, dto: UpdateAuctionDto
) -> Response:
    try:
        command = UpdateAuctionCommand(**dto.model_dump())
        await service.update(session, auction_id, command, username)
    except service.AuctionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
    except service.NotAuctionSellerError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from None
    return Response(status_code=status.HTTP_200_OK)


@router.delete("/{auction_id}")
async def delete_auction(
    session: Session, username: CurrentUsername, auction_id: UUID
) -> Response:
    try:
        await service.delete(session, auction_id, username)
    except service.AuctionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
    except service.NotAuctionSellerError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from None
    return Response(status_code=status.HTTP_200_OK)
