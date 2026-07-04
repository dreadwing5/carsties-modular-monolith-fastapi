# Carsties — Python Modular Monolith

A Python/FastAPI replica of the [Carsties .NET microservices tutorial](../carsties-microservices),
restructured as a **modular monolith** following the mapping in
[`docs/python_modular_monolith.md`](../carsties-microservices/docs/python_modular_monolith.md):
one deployable, hard module boundaries, and integration events — so extracting a
module back out to a microservice later is mechanical.

## How the .NET services map here

| .NET microservice | Here | Notes |
|---|---|---|
| `Carsties.AuctionService` | `modules/auctions` | FastAPI router + SQLAlchemy (Postgres `auctions` schema) + Alembic; outbox table + poller replaces the MassTransit EF outbox |
| `Carsties.SearchService` | `modules/search` | MongoDB read model; consumers subscribe to the in-process event bus instead of RabbitMQ |
| `Carsties.IdentityService` (Duende) | Keycloak container | External OIDC provider; the app only validates its JWTs (`shared/auth.py`) |
| `Carsties.Contracts` | each module's `contract.py` | The only file other modules may import — enforced by import-linter |
| MassTransit + RabbitMQ | `shared/events.py` | In-process pub/sub with retries and `Fault` publishing; swap for FastStream/RabbitMQ to go back to microservices |

## Project layout

```
├── pyproject.toml           # ≈ .sln + Directory.Build.props (uv project)
├── .importlinter            # ≈ project-reference rules — module boundaries in CI
├── alembic/                 # ≈ EF Core migrations (InitialCreate, Outbox)
├── docker-compose.yml       # postgres, mongodb, keycloak
├── keycloak/                # realm import: users alice/bob/tom, client "postman"
├── .vscode/                 # debug config, tasks, recommended extensions
├── src/carsties/
│   ├── main.py              # ≈ Program.cs
│   ├── shared/              # ≈ SharedKernel: settings, db, event bus, auth
│   └── modules/
│       ├── auctions/        # api / application / infrastructure / domain / contract.py
│       └── search/          # api / application / infrastructure / contract.py
└── tests/
```

## Prerequisites

- **Python 3.12+** — [download](https://www.python.org/downloads/)
- **Docker Desktop** — [download](https://www.docker.com/products/docker-desktop/)
- **[uv](https://docs.astral.sh/uv/)** (recommended) — `pip install uv`, or use plain `pip` (see below)

> ⚠️ The .NET Carsties repo's docker-compose binds the same host ports
> (Postgres `5433`, Mongo `27017`). Stop that stack before starting this one.

## Running it

### 1. Start the infrastructure

```bash
docker compose up -d
```

This starts:

| Container | Port | Purpose |
|---|---|---|
| postgres:17 | `5433` | auctions write model |
| mongo | `27017` | search read model |
| keycloak | `5001` | identity provider (realm `carsties` auto-imported) |

Keycloak takes ~30–60 s on first start. It's ready when
<http://localhost:5001/realms/carsties/.well-known/openid-configuration> returns JSON.

### 2. Install dependencies

With uv:

```bash
uv venv
uv pip install -e . --group dev
```

Or with plain pip:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -e . --group dev
```

### 3. Run the API

```bash
.venv\Scripts\python -m uvicorn carsties.main:app --reload --port 8000
```

On startup the app:

1. runs the Alembic migrations (≈ `Database.Migrate()`),
2. seeds the same ten auctions as the .NET version (same GUIDs),
3. creates the Mongo text index and syncs the search read model from the auctions module,
4. starts the outbox poller (every 10 s, ≈ MassTransit `QueryDelay`).

Open **Swagger UI** at <http://localhost:8000/docs>.

### 4. Try it

Public endpoints:

```bash
curl http://localhost:8000/api/auctions
curl "http://localhost:8000/api/search?searchTerm=ford&orderBy=make&pageSize=10"
curl http://localhost:8000/health
```

Get a token (same resource-owner-password flow the .NET version exposed for
Postman; users `alice` / `bob` / `tom`, password `Pass123$`):

```bash
curl -X POST http://localhost:5001/realms/carsties/protocol/openid-connect/token \
  -d grant_type=password -d client_id=postman -d client_secret=NotASecret \
  -d username=bob -d "password=Pass123$" -d "scope=openid profile"
```

Create an auction with the `access_token` from the response:

```bash
curl -X POST http://localhost:8000/api/auctions \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"make":"Tesla","model":"Model S","color":"Blue","year":2024,"mileage":100,
       "imageUrl":"https://example.com/tesla.jpg","reservePrice":40000,
       "auctionEnd":"2026-09-01T00:00:00Z"}'
```

Within ~10 s the outbox poller publishes `AuctionCreated`, the search consumer
upserts Mongo, and the car shows up in `GET /api/search?searchTerm=tesla`.
Only the seller can `PUT`/`DELETE` their auction (401 without a token,
403 as the wrong user) — same rules as the .NET service.

### The event flow

```
POST /api/auctions
  └─ auction row + AuctionCreated outbox row      (one Postgres transaction)
       └─ outbox poller (10s)                      ≈ MassTransit outbox delivery
            └─ event bus                           ≈ RabbitMQ
                 └─ search consumer → MongoDB      ≈ SearchService consumer
                      └─ GET /api/search
```

## Checks

```bash
.venv\Scripts\lint-imports              # ≈ compiler-enforced project references
.venv\Scripts\ruff check .              # lint + import order
.venv\Scripts\python -m mypy src        # strict typing (≈ the C# compiler)
.venv\Scripts\python -m pytest          # unit tests
```

(with uv: `uv run lint-imports`, `uv run ruff check .`, `uv run mypy src`, `uv run pytest`)

## VS Code

Open the folder and install the recommended extensions when prompted
(Python, Ruff, Mypy, Docker). Preconfigured for you:

- **F5** → *Carsties API (uvicorn --reload)* — run/debug the app with breakpoints
- **Testing sidebar** — pytest is auto-discovered from `tests/`
- **Terminal → Run Task…** — `infra: docker compose up`, `check: all`, etc.
- Format-on-save + import organizing via Ruff

## Configuration

Settings load from environment variables (prefix `CARSTIES_`) or a `.env` file —
see [`.env.example`](.env.example). Defaults match `docker-compose.yml`, so no
`.env` is needed for local development.

## Further reading

The [`docs/`](docs/README.md) folder has guides for the next steps:
[OpenTelemetry](docs/observability-opentelemetry.md) ·
[logging practices](docs/logging.md) ·
[an automatic auditing layer](docs/auditing.md) ·
[why there's no repository pattern](docs/repository-pattern.md).

## Troubleshooting

- **`invalid_scope` from Keycloak** — the realm didn't import (e.g. the container
  existed before the realm file): `docker compose up -d --force-recreate keycloak`.
- **Port already in use** — stop the .NET Carsties compose stack (shares 5433/27017),
  or anything else on 5001/8000.
- **Start completely fresh** — `docker compose down -v` wipes the Postgres and
  Mongo volumes; the app re-migrates and re-seeds on next startup.
