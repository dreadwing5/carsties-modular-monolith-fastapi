# Logging Practices

This codebase uses **structlog** layered over stdlib `logging`. The goal:
every log line is a structured event carrying the request/user/trace context,
not an interpolated string.

## 1. Principles (framework-agnostic)

- **Log events, not sentences.** `auction_created` with `auction_id=...`,
  `seller=...` beats `"Auction 47… was created by bob"`. Fields are queryable;
  prose isn't.
- **Bind context once, not on every call.** Request id, username and trace id
  are bound at the edge (middleware); handlers just log their event.
- **Levels:** `DEBUG` local diagnosis · `INFO` state changes / business events
  (created, deleted, consumed) · `WARNING` handled anomalies (retry, 4xx-worthy
  input) · `ERROR` failed operation with stack trace · never log-and-rethrow
  (one exception, one log).
- **Never log secrets or tokens.** JWTs, passwords, connection strings. Log the
  *username*, not the token that proved it.
- **Human-readable console in dev, JSON in prod.** Same events, different renderer.
- **Don't log payloads wholesale.** Log ids + the few fields a support engineer
  needs. (The audit layer — see [auditing.md](auditing.md) — is the place for
  full change capture, not the log stream.)

## 2. structlog setup

```toml
# pyproject.toml
dependencies = ["structlog>=24.1"]
```

Create `src/carsties/shared/logging.py` and call `configure_logging()` first
thing in `main.py` (replacing the current `logging.basicConfig`):

```python
"""Logging configuration — processors, renderer, level filtering."""

import logging
import structlog


def configure_logging(json_output: bool = False) -> None:
    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,   # request-scoped fields (see §3)
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
```

Usage — same shape everywhere, one module-level logger per file:

```python
import structlog

logger = structlog.get_logger(__name__)

logger.info("auction_created", auction_id=str(auction.id), seller=auction.seller)
logger.warning("consumer_retry", event="AuctionCreated", attempt=2, max=6)
logger.exception("outbox_poll_failed")   # ERROR + stack trace
```

## 3. Request context: bind once per request

`structlog.contextvars` uses Python `ContextVar`s, which flow correctly
through `async`/`await`. One middleware binds the fields; every log line in
that request — including inside SQLAlchemy or consumer code — carries them:

```python
# main.py
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=str(uuid.uuid4()),
            method=request.method,
            path=request.url.path,
        )
        return await call_next(request)


app.add_middleware(RequestContextMiddleware)
```

Bind the username the moment it's known — one line inside
`shared/auth.py::get_current_username`, right before `return username`:

```python
structlog.contextvars.bind_contextvars(username=username)
```

For work that *isn't* a request (the outbox poller, startup sync), bind the
equivalent identifiers at the top of the unit of work:

```python
structlog.contextvars.bind_contextvars(outbox_message_id=str(message.id),
                                       event_type=message.event_type)
```

## 4. Trace correlation

If OpenTelemetry is configured
([observability-opentelemetry.md](observability-opentelemetry.md)), add the ids
to every event so you can jump from a log line to the trace:

```python
from opentelemetry import trace

def add_trace_ids(logger, method_name, event_dict):
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict
```

…and insert `add_trace_ids` into the processor list before the renderer.

## 5. Taming uvicorn / third-party loggers

stdlib loggers (uvicorn, sqlalchemy, alembic, pymongo) still work — set their
levels rather than silencing them globally:

```python
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)   # our middleware logs requests
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)  # INFO = every SQL statement
```

Turn `sqlalchemy.engine` up to `INFO` temporarily when you need to see every
SQL statement the app issues.

## 6. What good looks like here

| Place | Event | Fields |
|---|---|---|
| `auctions/application/service.py` | `auction_created` / `auction_updated` / `auction_deleted` | `auction_id` (seller/username come from bound context) |
| `search/application/consumers.py` | `search_item_upserted` / `search_item_deleted` | `auction_id`, `event_type` |
| `shared/events.py` | `handler_retry`, `handler_faulted` | `event_type`, `attempt`, `handler` |
| `auctions/infrastructure/outbox.py` | `outbox_dispatched` | `outbox_message_id`, `event_type`, `lag_ms` |

`lag_ms` (now − `created_at` at dispatch) is the one metric-ish log field worth
having from day one: it tells you whether the outbox is keeping up.
