"""≈ Carsties.SearchService.Endpoints.SearchEndpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from carsties.modules.search.api.schemas import SearchItemDto, SearchResultDto
from carsties.modules.search.application.queries import build_search, clamp_paging
from carsties.modules.search.infrastructure import repository

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResultDto, response_model_by_alias=True)
async def search_items(
    search_term: Annotated[str | None, Query(alias="searchTerm")] = None,
    page_number: Annotated[int | None, Query(alias="pageNumber", ge=1)] = None,
    page_size: Annotated[int | None, Query(alias="pageSize", ge=1)] = None,
    seller: str | None = None,
    winner: str | None = None,
    order_by: Annotated[str | None, Query(alias="orderBy")] = None,
    filter_by: Annotated[str | None, Query(alias="filterBy")] = None,
) -> SearchResultDto:
    query_filter, sort = build_search(
        search_term=search_term,
        order_by=order_by,
        filter_by=filter_by,
        seller=seller,
        winner=winner,
        now=datetime.now(UTC),
    )
    page_number, page_size = clamp_paging(page_number, page_size)

    results, page_count, total_count = await repository.paged_search(
        query_filter, sort, page_number, page_size
    )

    return SearchResultDto(
        results=[SearchItemDto.from_document(doc) for doc in results],
        page_count=page_count,
        total_count=total_count,
    )
