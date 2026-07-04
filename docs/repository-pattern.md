# Do we need the Repository pattern?

**No — and for the same reason you didn't need it in the .NET version.**

The .NET AuctionService injected `AuctionDbContext` straight into its minimal
API endpoints. Nobody wrapped EF Core in `IAuctionRepository`, because EF Core's
`DbContext`/`DbSet` **already is** a repository + unit of work. The exact same
argument holds here, because SQLAlchemy's `Session` is the same abstraction:

| Repository/UoW concern | EF Core | SQLAlchemy |
|---|---|---|
| Collection-like access to aggregates | `DbSet<Auction>` | `session.get(Auction, id)`, `select(Auction)` |
| Change tracking | `ChangeTracker` | identity map + attribute history |
| Unit of work / atomic commit | `SaveChanges()` | `session.commit()` (flush = one transaction) |
| Deferred execution / composition | `IQueryable` | `select()` constructs, composable before execution |

Wrapping one generic repository in another (`IRepository<T>` over `DbSet<T>`,
or `AuctionRepository` over `Session`) adds a layer that forwards calls and
slowly re-grows the ORM's API one method at a time (`get_by_id_with_item`,
`get_by_seller_ordered_by_make`, …). That's ceremony, not architecture.

## What this codebase does instead

- **`application/service.py` is the boundary.** Routers never touch the
  `Session` beyond passing it in; all queries and mutations live in service
  functions (`service.create`, `service.get_all`, …). That's the layer you'd
  have put repositories behind — with none of the indirection.
- **import-linter enforces it** (`api → application → infrastructure → domain`).
  In .NET the compiler stopped `Api` referencing `Infrastructure`; here the
  linter does. You don't need an interface to hide the ORM when the architecture
  rule *forbids reaching around the service layer* outright.
- **`search/infrastructure/repository.py` is not the Repository pattern** —
  there's no interface, no abstraction, no swap-ability promise. It's just a
  module of data-access functions for Mongo (the .NET version's
  `MongoDB.Entities` calls, grouped in one file). The name is descriptive, not
  ceremonial.

## When a real repository *would* earn its keep

Reach for the pattern only when you have the problem it solves:

1. **Rich domain model you want persistence-ignorant.** If `Auction` grows real
   invariants and you want pure-Python domain objects (no SQLAlchemy mapping),
   a repository translates between domain objects and ORM rows. This is the
   [Cosmic Python](https://www.cosmicpython.com/book/chapter_02_repository.html)
   argument — note their prerequisite is *a domain model worth isolating*.
   Carsties' auction CRUD isn't that (yet).
2. **Two backends for the same aggregate** (e.g. Postgres in prod, in-memory
   fake in unit tests). But testcontainers / SQLite make DB-backed tests cheap
   enough that faking the DB is rarely worth an abstraction layer.
3. **The same non-trivial query reused in many places.** Before adding a
   repository, try the cheaper fix: a query function in the application layer
   (that's exactly what `service.get_all` is).

If one module eventually earns it (say a future `bidding` module with real
invariants), add a repository **in that module only**. Modular monolith rule:
patterns are per-module decisions, not repo-wide mandates — the .NET reference
repo (kgrzybek) does exactly this, and the doc this project follows says the
same: *"add domain/application layers only where the business logic earns it."*

## The audit corollary

A classic motivation for forcing all writes through repositories is "so we have
one place to add auditing." [auditing.md](auditing.md) shows why that's
unnecessary here: SQLAlchemy's flush events are a deeper chokepoint than any
repository — they catch every ORM write even if someone bypasses the service
layer. The ORM already provides the seam; you don't have to build one.
