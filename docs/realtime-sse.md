# Real-time updates: SSE, one pipe for many event types

Goal: a frontend that sees a new auction appear (or a bid land) **without
polling** `GET /api/search` every few seconds. This doc adds Server-Sent
Events (SSE) on top of the event bus, shows how *one* HTTP connection carries
*many* event types, and how to grow it into a proper real-time service.

## 1. Why SSE (and when WebSockets instead)

| | SSE | WebSockets |
|---|---|---|
| Direction | server → client only | both ways |
| Protocol | plain HTTP response that never ends | separate upgrade protocol |
| Auto-reconnect | built into `EventSource` (with `Last-Event-ID`) | you build it |
| Works through proxies/LBs | yes (it's just HTTP) | usually, with config |
| Fit here | pushing integration events to browsers | chat, live bidding *input* |

Everything this app currently needs to push (*"an auction was created /
updated / deleted"*) is one-directional — SSE is the simpler, sufficient
choice. If a `bidding` module later needs sub-second client → server traffic,
add a WebSocket endpoint *in that module*; the fan-out layer below is reused
either way.

## 2. The architecture — a third subscriber on the same chokepoint

Events already flow `outbox → event bus → consumers`. Real-time is just one
more consumer, exactly like the audit layer's option B — **no producer
changes**:

```
POST /api/auctions
  └─ outbox row ── poller ──► event bus ──► search consumer  → MongoDB
                                       ├──► audit subscriber → audit log
                                       └──► broadcaster      → every open SSE connection
```

### The broadcaster — `shared/broadcast.py`

One process-wide object; each connected client is an `asyncio.Queue`:

```python
import asyncio
from dataclasses import dataclass, field

Message = tuple[str, str]  # (event name, JSON data)


@dataclass
class Broadcaster:
    _clients: set[asyncio.Queue[Message]] = field(default_factory=set)

    def connect(self) -> asyncio.Queue[Message]:
        queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=100)
        self._clients.add(queue)
        return queue

    def disconnect(self, queue: asyncio.Queue[Message]) -> None:
        self._clients.discard(queue)

    async def publish(self, event_name: str, data: str) -> None:
        for queue in list(self._clients):
            try:
                queue.put_nowait((event_name, data))
            except asyncio.QueueFull:
                # A client that can't keep up gets dropped, not awaited —
                # one slow consumer must never stall the bus handler.
                self.disconnect(queue)


broadcaster = Broadcaster()
```

### Wiring — one line per event type, in `main.py`

```python
from carsties.shared.broadcast import broadcaster

async def _forward(event) -> None:
    await broadcaster.publish(type(event).__name__, event.model_dump_json())

for event_type in (AuctionCreated, AuctionUpdated, AuctionDeleted):
    event_bus.subscribe(event_type, _forward)
```

## 3. One pipe, many event types

This is the part SSE gives you for free. The wire format has an `event:`
field per message, so a single response stream multiplexes every type:

```
event: AuctionCreated
id: 42
data: {"id":"…","make":"Tesla","model":"Model S",…}

event: AuctionDeleted
id: 43
data: {"id":"…"}
```

The endpoint (using [`sse-starlette`](https://github.com/sysid/sse-starlette),
`pip install sse-starlette`):

```python
# a new module: src/carsties/modules/notifications/api/router.py
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/stream")
async def stream(request: Request) -> EventSourceResponse:
    queue = broadcaster.connect()

    async def events():
        try:
            while True:
                event_name, data = await queue.get()
                yield {"event": event_name, "data": data}
        finally:
            broadcaster.disconnect(queue)

    return EventSourceResponse(events(), ping=15)  # keep-alive comment every 15s
```

The browser subscribes **per type** on the one connection — no client-side
switch statement, no second socket per concern:

```js
const source = new EventSource("/api/notifications/stream");
source.addEventListener("AuctionCreated", (e) => addCard(JSON.parse(e.data)));
source.addEventListener("AuctionUpdated", (e) => patchCard(JSON.parse(e.data)));
source.addEventListener("AuctionDeleted", (e) => removeCard(JSON.parse(e.data)));
```

Adding a new event type later = one entry in the `_forward` loop + one
`addEventListener`. The pipe never changes.

### Per-user filtering

`EventSource` can't set an `Authorization` header. Options, in order of
preference: put the stream behind a cookie-authenticated session; pass a
short-lived token as a query param and validate it in the endpoint; or keep
the stream anonymous and only ever push *public* projections (what
`/api/search` would show anyway — a good default). For private streams
("your auction got a bid"), resolve the user in the endpoint and filter in
the generator before yielding.

## 4. Making it a real-time *service*

Grow it as a proper module, `modules/notifications/`, following the house
rules:

- it subscribes only to other modules' **contract** events (import-linter
  keeps it honest — add it to `.importlinter` with the same
  `ignore_imports` allowance for `auctions.contract` the search module has),
- it owns the `/api/notifications/stream` endpoint and the broadcaster,
- the gateway gets one more route: `GET /notifications/** → /api/notifications/**`
  (anonymous) in `gateway.py`'s `_ROUTES` — and its parity test.

Because the module touches nothing but events, extracting it later to a
standalone real-time service is the standard move: it consumes the same
events from a broker instead of the in-process bus, and the frontend points
its `EventSource` at the new host.

## 5. Scaling & operational notes

- **Multiple workers/instances break the in-process broadcaster** — a client
  connected to worker A never sees events consumed on worker B. The fix is
  the same as for the bus itself: fan out through something shared. Smallest
  step: Redis pub/sub — `_forward` publishes to a Redis channel; each
  instance runs one task that relays the channel into its local
  `broadcaster`. Everything else (endpoint, client code) is untouched.
- **Latency budget:** events reach the stream only after the outbox poller
  runs (`CARSTIES_OUTBOX_POLL_INTERVAL_SECONDS`, default 10 s). For snappier
  UX lower it, or wake the poller with Postgres `LISTEN/NOTIFY` instead of
  sleeping. Resist publishing to the broadcaster directly from the request —
  that's a dual write; if the transaction rolls back you've pushed a lie.
- **Proxy buffering kills SSE.** Behind nginx set `proxy_buffering off` (the
  app can also send `X-Accel-Buffering: no`); keep proxy read timeouts above
  the 15 s ping.
- **Reconnects are normal.** `EventSource` reconnects automatically; send
  `id:` fields and, if a gap matters, honor `Last-Event-ID` by replaying from
  a short in-memory ring buffer. For this app a reconnecting client can also
  just refetch `/api/search` — the read model *is* the catch-up mechanism.
- **Test it in-process** the way `tests/test_gateway.py` does: drive the app
  with `httpx.AsyncClient`, publish an event on the bus, assert the stream
  yields an `event: AuctionCreated` frame.
