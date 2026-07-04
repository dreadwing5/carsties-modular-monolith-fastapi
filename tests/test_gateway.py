"""Parity tests against the .NET GatewayService (YARP) route table."""

import httpx
from fastapi import FastAPI, Request

from carsties.gateway import GatewayMiddleware, match_route


def test_get_auctions_rewrites_anonymously():
    assert match_route("GET", "/auctions") == ("/api/auctions", False)
    assert match_route("GET", "/auctions/some-id") == ("/api/auctions/some-id", False)


def test_auction_writes_require_bearer():
    assert match_route("POST", "/auctions") == ("/api/auctions", True)
    assert match_route("PUT", "/auctions/some-id") == ("/api/auctions/some-id", True)
    assert match_route("DELETE", "/auctions/some-id") == ("/api/auctions/some-id", True)


def test_get_search_rewrites_anonymously():
    assert match_route("GET", "/search") == ("/api/search", False)


def test_unmatched_methods_and_paths_fall_through():
    assert match_route("PATCH", "/auctions/some-id") is None  # method not in route table
    assert match_route("POST", "/search") is None
    assert match_route("GET", "/api/auctions") is None  # module paths untouched
    assert match_route("GET", "/auctionsX") is None  # prefix must be a path segment


def _echo_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/auctions")
    @app.post("/api/auctions")
    @app.get("/api/search")
    async def echo(request: Request) -> dict[str, str]:
        return {"path": request.url.path}

    app.add_middleware(GatewayMiddleware)
    return app


async def test_middleware_rewrites_path():
    transport = httpx.ASGITransport(app=_echo_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/auctions")
        assert response.status_code == 200
        assert response.json() == {"path": "/api/auctions"}

        response = await client.get("/search")
        assert response.json() == {"path": "/api/search"}


async def test_middleware_blocks_anonymous_writes_at_the_edge():
    transport = httpx.ASGITransport(app=_echo_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auctions")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

        # with a bearer header present, the edge lets it through
        response = await client.post("/auctions", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == {"path": "/api/auctions"}
