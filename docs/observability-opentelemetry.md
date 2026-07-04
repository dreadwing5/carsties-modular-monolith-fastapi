# OpenTelemetry in the Carsties Monolith

In .NET you'd call `builder.Services.AddOpenTelemetry().WithTracing(...)` and get
ASP.NET Core, HttpClient and EF Core spans for free. Python has the same
auto-instrumentation story — one setup call in `main.py` plus one instrumentation
package per library.

## 1. Dependencies

```toml
# pyproject.toml
dependencies = [
    # ...
    "opentelemetry-sdk>=1.25",
    "opentelemetry-exporter-otlp>=1.25",
    "opentelemetry-instrumentation-fastapi>=0.46b0",
    "opentelemetry-instrumentation-sqlalchemy>=0.46b0",
    "opentelemetry-instrumentation-pymongo>=0.46b0",
    "opentelemetry-instrumentation-httpx>=0.46b0",
]
```

| .NET package | Python package |
|---|---|
| `OpenTelemetry.Instrumentation.AspNetCore` | `opentelemetry-instrumentation-fastapi` |
| `OpenTelemetry.Instrumentation.EntityFrameworkCore` | `opentelemetry-instrumentation-sqlalchemy` |
| `OpenTelemetry.Instrumentation.Http` | `opentelemetry-instrumentation-httpx` |
| `OpenTelemetry.Exporter.OpenTelemetryProtocol` | `opentelemetry-exporter-otlp` |
| `ActivitySource` / `Activity` | `trace.get_tracer(__name__)` / spans |

## 2. Setup module

Create `src/carsties/shared/telemetry.py` — the ≈ of the `AddOpenTelemetry()`
block in `Program.cs`:

```python
"""≈ builder.Services.AddOpenTelemetry() — tracing + metrics setup."""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from carsties.shared.database import get_engine


def configure_telemetry(app) -> None:
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "carsties"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # OTEL_EXPORTER_OTLP_ENDPOINT
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)                      # HTTP server spans
    SQLAlchemyInstrumentor().instrument(engine=get_engine().sync_engine)  # SQL spans
    PymongoInstrumentor().instrument()                           # Mongo command spans
```

Call it once in `main.py` after `app = FastAPI(...)`:

```python
from carsties.shared.telemetry import configure_telemetry

configure_telemetry(app)
```

Notes:

- For the **async** SQLAlchemy engine, instrument `engine.sync_engine` (the
  async engine is a wrapper around it).
- Pymongo instrumentation covers the `AsyncMongoClient` used by the search module.
- Configuration follows the standard env vars: `OTEL_EXPORTER_OTLP_ENDPOINT`,
  `OTEL_SERVICE_NAME`, `OTEL_TRACES_SAMPLER` — same ones .NET honours.

## 3. Tracing across the outbox / event bus

Auto-instrumentation stops at the HTTP request. The interesting Carsties trace —
`POST /api/auctions` → outbox commit → poller → search consumer → Mongo write —
crosses an async boundary, exactly like a MassTransit publish/consume pair. Two
additions make it one connected trace:

**a. Store the trace context in the outbox row** (≈ MassTransit propagating
`traceparent` in message headers). Add a `trace_context` column (or reuse a JSON
`headers` column) and capture it in `outbox.enqueue`:

```python
from opentelemetry.propagate import inject

def enqueue(session, event):
    carrier: dict[str, str] = {}
    inject(carrier)  # writes the W3C traceparent of the current span
    session.add(OutboxMessage(..., trace_context=json.dumps(carrier)))
```

**b. Resume it in the poller and wrap each dispatch in a consumer span:**

```python
from opentelemetry import trace
from opentelemetry.propagate import extract

tracer = trace.get_tracer("carsties.outbox")

# inside process_outbox_once, per message:
ctx = extract(json.loads(message.trace_context or "{}"))
with tracer.start_as_current_span(
    f"consume {message.event_type}",
    context=ctx,
    kind=trace.SpanKind.CONSUMER,
    attributes={"messaging.message.type": message.event_type},
):
    await event_bus.publish(event)
```

Now Jaeger shows the API request and the (up to 10 s later) consumer work as one
trace, with the outbox delay visible.

If a module is later extracted to a real microservice with FastStream/RabbitMQ,
the same `inject`/`extract` pair moves into message headers — nothing else changes.

## 4. Local backend

Add a collector + UI to `docker-compose.yml`. Jaeger all-in-one accepts OTLP
directly:

```yaml
  jaeger:
    image: jaegertracing/all-in-one:1.60
    ports:
      - 16686:16686   # UI  → http://localhost:16686
      - 4317:4317     # OTLP gRPC (the SDK's default endpoint)
```

Run the app with `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` (or nothing —
that's the default) and traces appear in the Jaeger UI.

## 5. What to add spans for manually

Auto-instrumentation covers HTTP/SQL/Mongo. Worth a manual span (a
`tracer.start_as_current_span(...)` context manager, ≈ `ActivitySource.StartActivity`):

- each event-bus handler (see §3) — it's your "consumer" span
- the startup search sync (`modules/search/application/sync.py`) — it can be slow
- retries in `shared/events.py` — add a span event per attempt so retry storms
  are visible

Rule of thumb: a span per *unit of work that can fail or be slow independently*,
attributes for the ids you'd grep logs for (`auction.id`, `event.type`).
