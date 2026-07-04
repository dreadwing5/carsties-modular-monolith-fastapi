# Modular Monolith in Python/FastAPI

How to structure a Python/FastAPI application as a modular monolith: the
concepts, a recommended toolchain, a concrete project layout, and repos to
study.

---

## 1. The big picture

A modular monolith is **one deployable, many modules with hard boundaries**.
Each module owns its domain, its data access, and its API surface, and other
modules may only talk to it through a small public contract (in-process
interface or events) — never by reaching into its internals.

The catch in Python: there are no compiler-enforced boundaries — everything can
import everything. So you enforce boundaries with **convention + a linter**
([`import-linter`](https://import-linter.readthedocs.io/)), which turns
cross-module imports into CI failures.

---

## 2. The building blocks and the tools for each

| Concern | Tool | Notes |
|---|---|---|
| Project/workspace | One `pyproject.toml` (or a [uv](https://docs.astral.sh/uv/) workspace) | uv gives you fast installs, a lockfile, and workspaces |
| Module | Python package (folder with `__init__.py`) per module | Boundary enforced by `import-linter`, not the interpreter |
| HTTP surface | FastAPI `APIRouter` per module | `app.include_router(auctions_router)` |
| Dependency injection | FastAPI `Depends()` for request scope; [`dependency-injector`](https://python-dependency-injector.ets-labs.org/) or [`lagom`](https://lagom-di.readthedocs.io/) for a full container | `Depends` covers ~80% of needs |
| ORM | [SQLAlchemy](https://www.sqlalchemy.org/) (`Session` / `AsyncSession`) | The de-facto standard; SQLModel is a Pydantic-flavored wrapper over it |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) | `alembic revision --autogenerate` |
| DTOs + validation + mapping | [Pydantic](https://docs.pydantic.dev/) models | `Model.model_validate(orm_obj)` maps ORM → DTO; validators live on the schema itself |
| Commands/queries bus | A simple hand-rolled command bus (~50 lines), or the message-bus pattern from the [Cosmic Python book](https://www.cosmicpython.com/) | No dominant library — and you rarely need one |
| Domain events (in-process) | Hand-rolled pub/sub or [`blinker`](https://blinker.readthedocs.io/) | This is how modules talk without coupling |
| Message broker (later) | [FastStream](https://faststream.ag2.ai/) or `aio-pika` (raw RabbitMQ) | FastStream gives you brokers, consumers, retries, DI |
| Outbox pattern | Roll your own: one table + one background poller | No turnkey library — and it's genuinely small |
| Background work | FastAPI `lifespan` + `asyncio.create_task`; [ARQ](https://arq-docs.helpmanual.io/) / [Dramatiq](https://dramatiq.io/) / Celery for real job queues | ARQ is the lightweight async choice |
| Settings | [`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) (`BaseSettings`) | Typed settings from env vars / `.env`, per module if you want |
| Structured logging | [structlog](https://www.structlog.org/) over stdlib `logging` | Bind request/user context once, log events not sentences |
| Identity | External IdP (Keycloak / Auth0) + `pyjwt` for validation; [Authlib](https://authlib.org/) to *build* an OIDC provider; [fastapi-users](https://fastapi-users.github.io/fastapi-users/) for app-level auth | Validating JWTs from an external IdP is a few lines with FastAPI security deps |
| Tests | [pytest](https://docs.pytest.org/) + `unittest.mock` + plain `assert` | Fixtures compose; parametrize covers table-driven cases |
| Containerized test deps | [testcontainers-python](https://testcontainers-python.readthedocs.io/) | Real Postgres/Mongo per test session |
| In-process API tests | FastAPI `TestClient` / `httpx.AsyncClient(transport=ASGITransport(app))` | Integration tests without a server |
| Architecture rules | [**import-linter**](https://import-linter.readthedocs.io/) | **The single most important tool for a Python modular monolith** — enforces module boundaries in CI |
| Type safety | [mypy](https://mypy-lang.org/) or [pyright](https://microsoft.github.io/pyright/) (strict mode) | Non-negotiable for a large codebase; treat errors as build failures |
| Lint/format | [Ruff](https://docs.astral.sh/ruff/) | One tool replaces flake8/isort/black |
| HTTP client + resilience | [httpx](https://www.python-httpx.org/) + [tenacity](https://tenacity.readthedocs.io/) (retries) | Async-first, connection pooling |
| gRPC | `grpcio` + `grpcio-tools` | If you need binary RPC between future services |
| Health checks | A `/health` router per module + aggregate endpoint | Trivial to hand-roll |

---

## 3. Recommended project structure

One package per module, with layers inside each module only where the domain
earns them:

```
myapp/
├── pyproject.toml               # project + dependency config
├── .importlinter                # module-boundary rules (the compiler you don't have)
├── alembic/                     # migrations (can be split per module)
├── src/
│   └── myapp/
│       ├── main.py              # entry point — builds app, includes module routers
│       ├── shared/              # shared kernel
│       │   ├── database.py      #   engine, session factory, Base
│       │   ├── events.py        #   in-process event bus (pub/sub)
│       │   ├── mediator.py      #   command/query bus (optional)
│       │   └── settings.py      #   BaseSettings
│       └── modules/
│           ├── auctions/
│           │   ├── api/                     #   HTTP surface
│           │   │   ├── router.py            #     APIRouter
│           │   │   └── schemas.py           #     Pydantic request/response DTOs
│           │   ├── application/             #   use cases
│           │   │   ├── commands.py          #     command handlers
│           │   │   └── queries.py           #     query handlers
│           │   ├── domain/                  #   the model
│           │   │   ├── entities.py          #     aggregates, entities, VOs
│           │   │   └── events.py            #     domain events
│           │   ├── infrastructure/          #   persistence & IO
│           │   │   ├── models.py            #     SQLAlchemy models
│           │   │   └── repository.py        #     data-access functions
│           │   └── contract.py              #   public API + integration events —
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

- **`contract.py` is the linchpin.** It exports the module's public façade (a
  few functions/interfaces) and its integration event types. Everything else in
  the module is private.
- **Small apps can flatten the layers**: `router.py`, `service.py`, `models.py`,
  `schemas.py`, `repository.py` per module (this is the structure from
  [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices),
  the most-starred FastAPI structure guide). Add the DDD layers only in modules
  whose domain justifies them.
- **Per-module DB isolation**: use one database with a **schema per module**
  (Postgres schemas) so no module can join across another module's tables.

### Enforcing boundaries — `.importlinter`

Run `lint-imports` in CI and boundary violations become build failures:

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

# Layering inside each module
[importlinter:contract:auctions-layers]
name = Auctions layered architecture
type = layers
layers =
    myapp.modules.auctions.api
    myapp.modules.auctions.application
    myapp.modules.auctions.infrastructure
    myapp.modules.auctions.domain
```

### Wiring modules in `main.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from myapp.modules.auctions.api.router import router as auctions_router
from myapp.modules.bidding.api.router import router as bidding_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: init DB, subscribe event handlers, start outbox poller
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(auctions_router, prefix="/api/auctions", tags=["auctions"])
app.include_router(bidding_router, prefix="/api/bidding", tags=["bidding"])
```

### Module-to-module communication

Two options, in order of preference:

1. **In-process events**: auctions publishes `AuctionFinished`, bidding
   subscribes. Keeps modules decoupled and makes a later extraction to
   microservices mechanical (swap the in-process bus for RabbitMQ/FastStream —
   the handlers don't change).
2. **Direct call through the contract**:
   `from myapp.modules.auctions.contract import get_auction_status`. Fine for
   queries; avoid for writes.

Never: `from myapp.modules.auctions.infrastructure.models import Auction` in
the bidding module. import-linter will fail the build.

---

## 4. The toolchain at a glance

| Purpose | Tool |
|---|---|
| Runtime/framework | FastAPI + Uvicorn |
| Package/build | **uv** |
| ORM + migrations | SQLAlchemy + Alembic |
| Validation/DTOs | Pydantic |
| Type safety | mypy/pyright (strict) — treat errors as build failures |
| Lint/format | Ruff |
| Architecture rules | import-linter |
| Tests | pytest, unittest.mock, testcontainers-python |
| Messaging | FastStream / aio-pika |
| Background jobs | lifespan tasks, ARQ, Celery |
| Config | pydantic-settings |
| Logging | structlog |
| Resilience | tenacity |

---

## 5. Repositories to study

**Python / FastAPI modular monoliths:**

- [arctikant/fastapi-modular-monolith-starter-kit](https://github.com/arctikant/fastapi-modular-monolith-starter-kit) — FastAPI template built explicitly on modular monolith + layered architecture principles. Closest to a ready-made starting point.
- [Khaled-Farhat/modular-monolith-practice](https://github.com/Khaled-Farhat/modular-monolith-practice) — three modules (Users, Orders, Catalog), each deliberately using a different style (Layered, Hexagonal, Clean); cross-module access only via a shared public API. Great for comparing the styles.
- [YoraiLevi/modular-monolith-fastapi](https://github.com/YoraiLevi/modular-monolith-fastapi) — modern tooling showcase (uv, ruff, pyright, SQLModel) using FastAPI sub-application mounts as module boundaries.
- [pgorecki/python-ddd](https://github.com/pgorecki/python-ddd) — **an online auction system** (listings, bidding, payments bounded contexts) with full DDD tactical patterns and a companion blog at [dddinpython.com](https://dddinpython.com/).
- [qu3vipon/python-ddd](https://github.com/qu3vipon/python-ddd) and [NEONKID/fastapi-ddd-example](https://github.com/NEONKID/fastapi-ddd-example) — smaller FastAPI DDD layouts.
- [Netflix/dispatch](https://github.com/Netflix/dispatch) — production FastAPI app organized as packages-per-domain (flat structure, no DDD layers). The best real-world example of "module = folder with router/service/models/schemas."
- [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices) — not a monolith itself, but the community-standard guide to module-per-package FastAPI structure.

**Books/guides:**

- [Cosmic Python (Architecture Patterns with Python)](https://www.cosmicpython.com/) — free online book; repository pattern, unit of work, message bus, and events in idiomatic Python.

---

## 6. Practical advice

1. **Don't over-layer.** Ceremony (interfaces everywhere, one class per file) reads as noise in Python. Start with flat modules (router/service/models/schemas) and add domain/application layers only where the business logic earns it.
2. **import-linter from day one.** It's the only thing standing between you and a big ball of mud — nothing else will stop cross-module imports.
3. **Strict typing from day one.** `mypy --strict` or pyright strict catches whole classes of bugs before runtime.
4. **Pydantic does triple duty** (DTOs, validation, mapping). Lean into it instead of adding separate validator/mapper libraries.
5. **Async all the way down.** FastAPI + SQLAlchemy 2.0 async + httpx keep the whole request path non-blocking.
6. **Design module contracts as if they were integration events.** If a module boundary would survive being replaced by RabbitMQ, it's a good boundary.
