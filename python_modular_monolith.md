# Modular Monolith in Python/FastAPI — a .NET Developer's Map

If you know how a .NET modular monolith is structured (solution → projects → Clean Architecture layers, MediatR, EF Core, built-in DI), this doc maps every one of those concepts to its Python/FastAPI equivalent, then shows a concrete project layout and repos to study.

---

## 1. The big picture

A modular monolith is the same idea in both ecosystems: **one deployable, many modules with hard boundaries**. Each module owns its domain, its data access, and its API surface, and other modules may only talk to it through a small public contract (in-process interface or events) — never by reaching into its internals.

The key difference: .NET enforces boundaries with **separate projects/assemblies** (`Auctions.Domain.csproj` can't reference `Bidding.Infrastructure` unless you add a reference). Python has no compiler-enforced project references — everything can import everything. So in Python you enforce boundaries with **convention + a linter** (`import-linter`), which plays the role of the .NET project-reference graph and NetArchTest.

---

## 2. Concept-by-concept mapping

| .NET concept | Python/FastAPI equivalent | Notes |
|---|---|---|
| Solution (`.sln`) | Repo with one `pyproject.toml` (or uv workspace) | uv/Poetry workspaces ≈ multi-project solutions |
| Project (`.csproj`) per module | Python package (folder with `__init__.py`) per module | Boundary enforced by `import-linter`, not compiler |
| ASP.NET Controllers / Minimal APIs | FastAPI `APIRouter` per module | `app.include_router(auctions_router)` |
| Built-in DI (`IServiceCollection`) | FastAPI `Depends()` for request scope; [`dependency-injector`](https://python-dependency-injector.ets-labs.org/) or [`lagom`](https://lagom-di.readthedocs.io/) for a real container | FastAPI's `Depends` covers ~80% of needs |
| EF Core (`DbContext`) | [SQLAlchemy](https://www.sqlalchemy.org/) ORM + `Session` / `AsyncSession` | The de-facto standard; SQLModel is a Pydantic-flavored wrapper over it |
| EF Core Migrations | [Alembic](https://alembic.sqlalchemy.org/) | `alembic revision --autogenerate` ≈ `dotnet ef migrations add` |
| DTOs + AutoMapper | [Pydantic](https://docs.pydantic.dev/) models | `Model.model_validate(orm_obj)` replaces AutoMapper — no mapper library needed |
| FluentValidation | Pydantic validators | Validation lives on the schema itself |
| MediatR (commands/queries) | No dominant library — a simple hand-rolled command bus, or [`mediatr` (pip)](https://pypi.org/project/mediatr/) / message bus pattern from the [Cosmic Python book](https://www.cosmicpython.com/) | Hand-rolled ~50 lines; Cosmic Python shows the canonical pattern |
| MediatR notifications (domain events) | In-process event bus (hand-rolled pub/sub) or [`blinker`](https://blinker.readthedocs.io/) | This is how modules talk without coupling |
| MassTransit + RabbitMQ | [FastStream](https://faststream.ag2.ai/) (closest spiritual match), or `aio-pika` (raw RabbitMQ) | FastStream gives you brokers, consumers, retries, DI like MassTransit |
| Outbox pattern (MassTransit EF Outbox) | Roll your own outbox table + poller, or FastStream + custom outbox | No turnkey equivalent — usually ~1 table + 1 background task |
| BackgroundService / IHostedService | FastAPI `lifespan` + `asyncio.create_task`, or [ARQ](https://arq-docs.helpmanual.io/) / [Dramatiq](https://dramatiq.io/) / Celery for real job queues | ARQ is the lightweight async choice; Celery ≈ Hangfire |
| `appsettings.json` + `IOptions<T>` | [`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) (`BaseSettings`) | Typed settings from env vars / `.env`, per module if you want |
| Serilog / `ILogger<T>` | [structlog](https://www.structlog.org/) (structured) or stdlib `logging` | structlog ≈ Serilog with enrichers |
| Duende IdentityServer | [Authlib](https://authlib.org/) (build an OAuth2/OIDC provider) or external: Keycloak / Auth0; [fastapi-users](https://fastapi-users.github.io/fastapi-users/) for app-level auth | Validating JWTs from an external IdP: `pyjwt` + FastAPI security deps |
| xUnit + Moq + FluentAssertions | [pytest](https://docs.pytest.org/) + `unittest.mock` + plain `assert` | pytest fixtures ≈ xUnit fixtures but more powerful |
| Testcontainers for .NET | [testcontainers-python](https://testcontainers-python.readthedocs.io/) | Same project, same idea |
| WebApplicationFactory | FastAPI `TestClient` / `httpx.AsyncClient(transport=ASGITransport(app))` | In-process integration tests, no server needed |
| NetArchTest / ArchUnitNET | [**import-linter**](https://import-linter.readthedocs.io/) | **The single most important tool for a Python modular monolith** — enforces module boundaries in CI |
| Roslyn analyzers / nullable refs | [mypy](https://mypy-lang.org/) or [pyright](https://microsoft.github.io/pyright/) (strict mode) | Non-negotiable for a large codebase |
| `dotnet format` / StyleCop | [Ruff](https://docs.astral.sh/ruff/) (lint + format) | One tool replaces flake8/isort/black |
| NuGet + `dotnet` CLI | [uv](https://docs.astral.sh/uv/) | uv ≈ the modern `dotnet` CLI experience (fast, lockfile, workspaces) |
| `IHttpClientFactory` + Polly | [httpx](https://www.python-httpx.org/) + [tenacity](https://tenacity.readthedocs.io/) (retries) | tenacity ≈ Polly |
| gRPC (`Grpc.AspNetCore`) | `grpcio` + `grpcio-tools` | Same protos work across both |
| Health checks (`AspNetCore.Diagnostics.HealthChecks`) | A `/health` router per module + aggregate endpoint | Trivial to hand-roll |

---

## 3. Recommended project structure

Mirrors a .NET modular monolith solution (one "project" per module × layer), collapsed into packages:

```
myapp/
├── pyproject.toml               # ≈ .sln + Directory.Build.props
├── .importlinter                # ≈ project-reference rules (the compiler you don't have)
├── alembic/                     # migrations (can be split per module)
├── src/
│   └── myapp/
│       ├── main.py              # ≈ Program.cs — builds app, includes module routers
│       ├── shared/              # ≈ SharedKernel / BuildingBlocks project
│       │   ├── database.py      #   engine, session factory, Base
│       │   ├── events.py        #   in-process event bus (pub/sub)
│       │   ├── mediator.py      #   command/query bus (optional)
│       │   └── settings.py      #   BaseSettings
│       └── modules/
│           ├── auctions/                    # ≈ Modules.Auctions.* projects
│           │   ├── api/                     #   ≈ Auctions.Api (controllers)
│           │   │   ├── router.py            #     APIRouter — the HTTP surface
│           │   │   └── schemas.py           #     Pydantic request/response DTOs
│           │   ├── application/             #   ≈ Auctions.Application
│           │   │   ├── commands.py          #     command handlers (MediatR-style)
│           │   │   └── queries.py           #     query handlers
│           │   ├── domain/                  #   ≈ Auctions.Domain
│           │   │   ├── entities.py          #     aggregates, entities, VOs
│           │   │   └── events.py            #     domain events
│           │   ├── infrastructure/          #   ≈ Auctions.Infrastructure
│           │   │   ├── models.py            #     SQLAlchemy models
│           │   │   └── repository.py        #     repository implementations
│           │   └── contract.py              #   ≈ Auctions.IntegrationEvents / public API
│           │                                #     the ONLY thing other modules may import
│           ├── bidding/
│           │   └── ... same shape ...
│           └── search/
│               └── ... same shape ...
└── tests/
    ├── auctions/
    ├── bidding/
    └── architecture/            # import-linter runs in CI instead
```

Notes:

- **`contract.py` is the linchpin.** It exports the module's public façade (a few functions/interfaces) and its integration event types. Everything else in the module is private. In .NET this is your `IntegrationEvents` project + `internal` access modifier.
- **Small apps can flatten the layers**: `router.py`, `service.py`, `models.py`, `schemas.py`, `repository.py` per module (this is the structure from [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices), the most-starred FastAPI structure guide). Add the DDD layers only in modules whose domain justifies them.
- **Per-module DB isolation**: use one database with a **schema per module** (Postgres schemas ≈ what kgrzybek's repo does) so no module can join across another module's tables.

### Enforcing boundaries — `.importlinter`

This replaces the .NET project-reference graph. Run `lint-imports` in CI and boundaries become build failures, just like in .NET:

```ini
[importlinter]
root_package = myapp

# Modules may not import each other's internals
[importlinter:contract:module-independence]
name = Modules are independent
type = independence
modules =
    myapp.modules.auctions
    myapp.modules.bidding
    myapp.modules.search
# allow contract.py imports via ignore_imports or a layered contract

# Clean Architecture layering inside each module
[importlinter:contract:auctions-layers]
name = Auctions layered architecture
type = layers
layers =
    myapp.modules.auctions.api
    myapp.modules.auctions.application
    myapp.modules.auctions.infrastructure
    myapp.modules.auctions.domain
```

### Wiring modules in `main.py` (≈ Program.cs)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from myapp.modules.auctions.api.router import router as auctions_router
from myapp.modules.bidding.api.router import router as bidding_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ≈ IHostedService startup: init DB, subscribe event handlers, start outbox poller
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(auctions_router, prefix="/api/auctions", tags=["auctions"])
app.include_router(bidding_router, prefix="/api/bidding", tags=["bidding"])
```

### Module-to-module communication

Same two options as .NET, in order of preference:

1. **In-process events** (≈ MediatR notifications): auctions publishes `AuctionFinished`, bidding subscribes. Keeps modules decoupled and makes a later extraction to microservices mechanical (swap the in-process bus for RabbitMQ/FastStream — the handlers don't change).
2. **Direct call through the contract** (≈ referencing another module's public interface): `from myapp.modules.auctions.contract import get_auction_status`. Fine for queries; avoid for writes.

Never: `from myapp.modules.auctions.infrastructure.models import Auction` in the bidding module. import-linter will fail the build.

---

## 4. The toolchain, side by side

| Purpose | .NET | Python |
|---|---|---|
| Runtime/framework | ASP.NET Core | FastAPI + Uvicorn |
| Package/build | dotnet CLI + NuGet | **uv** |
| ORM + migrations | EF Core | SQLAlchemy + Alembic |
| Validation/DTOs | FluentValidation, records | Pydantic |
| Type safety | C# compiler | mypy/pyright (strict) — treat errors as build failures |
| Lint/format | analyzers, dotnet format | Ruff |
| Architecture rules | project refs, NetArchTest | import-linter |
| Tests | xUnit, Moq, Testcontainers | pytest, unittest.mock, testcontainers-python |
| Messaging | MassTransit | FastStream / aio-pika |
| Background jobs | IHostedService, Hangfire | lifespan tasks, ARQ, Celery |
| Config | IOptions + appsettings | pydantic-settings |
| Logging | Serilog | structlog |
| Resilience | Polly | tenacity |

---

## 5. Repositories to study

**Python / FastAPI modular monoliths:**

- [arctikant/fastapi-modular-monolith-starter-kit](https://github.com/arctikant/fastapi-modular-monolith-starter-kit) — FastAPI template built explicitly on modular monolith + layered architecture principles. Closest to a ready-made starting point.
- [Khaled-Farhat/modular-monolith-practice](https://github.com/Khaled-Farhat/modular-monolith-practice) — three modules (Users, Orders, Catalog), each deliberately using a different style (Layered, Hexagonal, Clean); cross-module access only via a shared public API. Great for comparing the styles.
- [YoraiLevi/modular-monolith-fastapi](https://github.com/YoraiLevi/modular-monolith-fastapi) — modern tooling showcase (uv, ruff, pyright, SQLModel) using FastAPI sub-application mounts as module boundaries.
- [pgorecki/python-ddd](https://github.com/pgorecki/python-ddd) — **an online auction system** (listings, bidding, payments bounded contexts — essentially Carsties!) with full DDD tactical patterns and a companion blog at [dddinpython.com](https://dddinpython.com/).
- [qu3vipon/python-ddd](https://github.com/qu3vipon/python-ddd) and [NEONKID/fastapi-ddd-example](https://github.com/NEONKID/fastapi-ddd-example) — smaller FastAPI DDD layouts.
- [Netflix/dispatch](https://github.com/Netflix/dispatch) — production FastAPI app organized as packages-per-domain (flat structure, no DDD layers). The best real-world example of "module = folder with router/service/models/schemas."
- [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices) — not a monolith itself, but the community-standard guide to module-per-package FastAPI structure.

**The .NET reference (worth reading even for a Python build):**

- [kgrzybek/modular-monolith-with-ddd](https://github.com/kgrzybek/modular-monolith-with-ddd) — *the* canonical modular monolith repo. Its ADRs and README explain module isolation, contracts, outbox, and event-based integration better than anything else. Port its *decisions*, not its code.

**Books/guides:**

- [Cosmic Python (Architecture Patterns with Python)](https://www.cosmicpython.com/) — free online book; repository pattern, unit of work, message bus, and events in idiomatic Python. This is the closest thing Python has to the Ardalis/Jason Taylor Clean Architecture material.

---

## 6. Practical advice for the migration mindset

1. **Don't over-layer.** C#'s ceremony (interfaces everywhere, one class per file) is idiomatic there; in Python it reads as noise. Start with flat modules (router/service/models/schemas) and add domain/application layers only where the business logic earns it.
2. **import-linter from day one.** It's the only thing standing between you and a big ball of mud — Python won't stop cross-module imports the way missing project references do.
3. **Strict typing from day one.** `mypy --strict` or pyright strict gives you back most of what the C# compiler was doing for you.
4. **Pydantic replaces three .NET libraries** (DTOs, FluentValidation, AutoMapper). Lean into it.
5. **Async all the way down.** FastAPI + SQLAlchemy 2.0 async + httpx mirrors the async/await discipline you already have from C#.
6. **Design module contracts as if they were integration events.** If a module boundary would survive being replaced by RabbitMQ, it's a good boundary — same rule you applied in Carsties.
