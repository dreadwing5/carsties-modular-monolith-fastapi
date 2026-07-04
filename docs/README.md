# Carsties Docs

Guides for evolving the modular monolith. Each one maps the .NET concept you
already know to its Python equivalent and shows where it plugs into *this*
codebase.

| Doc | What it covers | .NET equivalent |
|---|---|---|
| [observability-opentelemetry.md](observability-opentelemetry.md) | Traces + metrics with OpenTelemetry, auto-instrumentation, tracing the outbox → event bus hop | `AddOpenTelemetry()`, Activity/ActivitySource |
| [logging.md](logging.md) | Structured logging with structlog, request/user/trace correlation, what (not) to log | Serilog + enrichers |
| [auditing.md](auditing.md) | An audit layer that records who did what, when — **without touching each action** | EF Core `SaveChanges` interceptors / temporal tables |
| [repository-pattern.md](repository-pattern.md) | Why this codebase has no repositories, and when you'd add one | "Do we still need `IRepository<T>` over EF Core?" |
