"""≈ Carsties.GatewayService — the YARP reverse proxy, collapsed into an ASGI
middleware.

In the microservices version YARP exposes the public route surface
(/auctions, /search), rewrites paths to each service's /api/... prefix, and
requires an authenticated user on auction writes before proxying. In the
monolith there is no second host to proxy to, so the same route table becomes
a path rewrite in front of the module routers:

    GET               /auctions/**  ->  /api/auctions/**   (anonymous)
    POST|PUT|DELETE   /auctions/**  ->  /api/auctions/**   (bearer required)
    GET               /search/**    ->  /api/search/**     (anonymous)

Anything that matches no route falls through untouched (and 404s, exactly like
YARP with no matching route). The edge check only requires that a bearer token
is *present* (≈ YARP rejecting anonymous requests); full validation of the
token still happens in the endpoint's auth dependency, so an invalid token is
still a 401 — just one layer deeper.
"""

from starlette.types import ASGIApp, Receive, Scope, Send

_ROUTES: tuple[tuple[str, frozenset[str], str, bool], ...] = (
    # (public prefix, methods, target prefix, requires bearer)
    ("/auctions", frozenset({"GET"}), "/api/auctions", False),
    ("/auctions", frozenset({"POST", "PUT", "DELETE"}), "/api/auctions", True),
    ("/search", frozenset({"GET"}), "/api/search", False),
)


def match_route(method: str, path: str) -> tuple[str, bool] | None:
    """Return (rewritten path, requires_bearer) or None if no gateway route."""
    for prefix, methods, target, requires_bearer in _ROUTES:
        if method in methods and (path == prefix or path.startswith(prefix + "/")):
            return target + path[len(prefix):], requires_bearer
    return None


def _has_bearer(scope: Scope) -> bool:
    for name, value in scope["headers"]:
        if name == b"authorization" and value[:7].lower() == b"bearer ":
            return True
    return False


class GatewayMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            route = match_route(scope["method"], scope["path"])
            if route is not None:
                path, requires_bearer = route
                if requires_bearer and not _has_bearer(scope):
                    await _unauthorized(send)
                    return
                scope = dict(scope)
                scope["path"] = path
                scope["raw_path"] = path.encode()
        await self.app(scope, receive, send)


async def _unauthorized(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"www-authenticate", b"Bearer"),
                (b"content-length", b"0"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b""})
