# Carsties Docs

Guides for evolving the modular monolith. Each one explains the concept, then
shows where it plugs into *this* codebase.

| Doc | What it covers |
|---|---|
| [python_modular_monolith.md](python_modular_monolith.md) | The architecture this project follows: modules, contracts, boundary enforcement, and the toolchain |
| [observability-opentelemetry.md](observability-opentelemetry.md) | Traces + metrics with OpenTelemetry, auto-instrumentation, tracing the outbox → event bus hop |
| [logging.md](logging.md) | Structured logging with structlog, request/user/trace correlation, what (not) to log |
| [auditing.md](auditing.md) | An audit layer that records who did what, when — **without touching each action** |
| [authorization.md](authorization.md) | Permission levels: roles from Keycloak, policy dependencies, resource ownership rules |
| [realtime-sse.md](realtime-sse.md) | Server-Sent Events: many event types over one pipe, and growing it into a real-time service |
| [azure-integration.md](azure-integration.md) | Function Apps, Cosmos DB and Blob Storage — where serverless and cloud storage plug in |
| [repository-pattern.md](repository-pattern.md) | Why this codebase has no repositories, and when you'd add one |
