# Auditing: who did what, when — without touching every action

Goal: answer questions like *"who created this auction?"*, *"what did bob do
yesterday?"*, *"when was auction X deleted, and by whom?"* — **without adding an
`audit(...)` call inside every endpoint or service function.**

The trick is the same one you'd use in .NET: don't instrument the actions,
instrument the **chokepoint they all pass through**. In EF Core that's a
`SaveChangesInterceptor`; in SQLAlchemy it's the **session flush events**. Every
insert, update and delete — current and future — flows through flush, so one
listener audits the whole write model forever.

## The three options

| Approach | ≈ .NET | Catches | Misses | Actor |
|---|---|---|---|---|
| **A. SQLAlchemy flush listener** (recommended) | `SaveChangesInterceptor` | every ORM insert/update/delete, incl. field-level diffs | raw SQL (`session.execute(update(...))`) | from a request-scoped `ContextVar` |
| B. Event-bus subscriber | audit consumer on RabbitMQ | business events (`AuctionCreated`, …) | actions that don't publish events; field diffs | only what the event carries |
| C. Postgres triggers | DB triggers / temporal tables | *everything*, even psql | app context (user, request id) unless smuggled via `SET LOCAL` | hard |

Use **A** as the backbone. Add **B** later if you want a *business-language*
audit ("auction won", "bid rejected") on top of the *data-language* one — it's a
one-line `bus.subscribe(...)` per event, still zero changes to handlers.

---

## A. The flush-listener audit layer

Three small pieces, all in the shared kernel. No module code changes except one
line in `auth.py`.

### 1. Request-scoped actor — `shared/request_context.py`

A `ContextVar` flows through `async/await` like `AsyncLocal<T>` (this is also
what `ICurrentUser`/`IHttpContextAccessor` gave you):

```python
from contextvars import ContextVar

current_actor: ContextVar[str | None] = ContextVar("current_actor", default=None)
current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)
```

Set the actor where authentication already happens — one line in
`shared/auth.py::get_current_username`, just before `return username`:

```python
current_actor.set(username)
```

Background work (outbox poller, startup sync, consumers) isn't a request; set
`current_actor.set("system:outbox")` etc. at the top of those loops so audit
rows are never anonymous.

### 2. The audit table — `shared/audit.py`

One append-only table in its own schema. `changes` holds a field-level diff for
updates and a snapshot for inserts/deletes:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from carsties.shared.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "audit"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String)          # "bob", "system:outbox"
    action: Mapped[str] = mapped_column(String)         # insert | update | delete
    entity_type: Mapped[str] = mapped_column(String)    # "Auction", "Item"
    entity_id: Mapped[str] = mapped_column(String)
    changes: Mapped[dict] = mapped_column(JSONB)        # {"color": ["Blue","Red"]}
    request_id: Mapped[str | None] = mapped_column(String)
```

Plus an Alembic migration (`0003_audit`): `CREATE SCHEMA audit` + the table +
indexes on `(entity_type, entity_id)` and `(actor, occurred_at)`.

### 3. The listener — the whole "layer"

The standard two-hook recipe: **collect diffs in `before_flush`** (attribute
history is still available), **write rows in `after_flush`** (primary keys of
new objects are assigned by then), on the same connection → **same
transaction** as the business change. An auction can't be deleted without its
audit row, and vice versa.

```python
from datetime import UTC, datetime

from sqlalchemy import event, inspect, insert
from sqlalchemy.orm import Session

from carsties.shared.request_context import current_actor, current_request_id

_SKIP = {"AuditLog", "OutboxMessage"}   # never audit the audit (or the plumbing)


def _diff(obj) -> dict:
    changes = {}
    for attr in inspect(obj).attrs:
        history = attr.load_history()
        if history.has_changes():
            old = history.deleted[0] if history.deleted else None
            new = history.added[0] if history.added else None
            changes[attr.key] = [_scalar(old), _scalar(new)]
    return changes


def _snapshot(obj) -> dict:
    mapper = inspect(obj).mapper
    return {c.key: _scalar(getattr(obj, c.key)) for c in mapper.column_attrs}


def _scalar(value):
    return value.isoformat() if isinstance(value, datetime) else \
           value.value if hasattr(value, "value") else \
           str(value) if value is not None and not isinstance(value, (str, int, float, bool)) else value


@event.listens_for(Session, "before_flush")
def _collect(session, flush_context, instances):
    pending = session.info.setdefault("audit_pending", [])
    for obj in session.dirty:
        if type(obj).__name__ not in _SKIP and session.is_modified(obj):
            pending.append((obj, "update", _diff(obj)))
    for obj in session.deleted:
        if type(obj).__name__ not in _SKIP:
            pending.append((obj, "delete", _snapshot(obj)))
    for obj in session.new:
        if type(obj).__name__ not in _SKIP:
            pending.append((obj, "insert", None))   # snapshot after PKs exist


@event.listens_for(Session, "after_flush")
def _write(session, flush_context):
    pending = session.info.pop("audit_pending", [])
    if not pending:
        return
    from carsties.shared.audit import AuditLog
    rows = [
        {
            "occurred_at": datetime.now(UTC),
            "actor": current_actor.get() or "anonymous",
            "action": action,
            "entity_type": type(obj).__name__,
            "entity_id": str(inspect(obj).identity[0]) if inspect(obj).identity else "?",
            "changes": changes if changes is not None else _snapshot(obj),
            "request_id": current_request_id.get(),
        }
        for obj, action, changes in pending
    ]
    session.execute(insert(AuditLog), rows)
```

Registering the listener on the **sync `Session` class** covers the async
sessions too — `AsyncSession` is a wrapper around it. Import this module once
from `main.py` (`import carsties.shared.audit  # registers listeners`) and
you're done.

### What you get, for free, everywhere

```sql
-- who created auction X?
SELECT actor, occurred_at FROM audit.audit_log
 WHERE entity_type = 'Auction' AND entity_id = :id AND action = 'insert';

-- when was it deleted, by whom, and what did it look like?
SELECT actor, occurred_at, changes FROM audit.audit_log
 WHERE entity_type = 'Auction' AND entity_id = :id AND action = 'delete';

-- everything bob did today
SELECT occurred_at, action, entity_type, entity_id, changes
  FROM audit.audit_log
 WHERE actor = 'bob' AND occurred_at > now() - interval '1 day'
 ORDER BY occurred_at;
```

And when you add a `bidding` module next month, its entities are audited the
moment they exist — no one has to remember anything.

---

## B. Business-level audit via the event bus (optional layer on top)

The integration events already describe *what happened* in domain language, and
the bus is another chokepoint. A single subscriber gives you a second audit
stream without touching any producer:

```python
# shared/audit_events.py
async def audit_event(event) -> None:
    await audit_store.append(
        kind=type(event).__name__,
        actor=current_actor.get() or "system",
        payload=event.model_dump(mode="json"),
    )

def register_audit(bus: EventBus) -> None:
    for event_type in (AuctionCreated, AuctionUpdated, AuctionDeleted):
        bus.subscribe(event_type, audit_event)
```

Caveats: it only sees actions that publish events, and events are consumed by
the outbox poller — so the actor there is `system:outbox` unless you carry the
actor *inside* the event (add an `initiated_by` field to the contracts if you
need it). That's why option A is the backbone: the flush listener runs in the
original request, where the real user is still in context.

## Mongo (search module)?

Usually **no** — the search read model is a projection; its source of truth is
the auctions write model, which is already audited. Auditing derived data
doubles the storage for zero forensic value. If you ever need it, the pymongo
equivalent chokepoint is wrapping `repository.save/update_fields/delete` — three
functions, still not per-action code.

## Practicalities

- **Retention:** append-only tables grow forever. Partition by month
  (`pg_partman`) or schedule `DELETE WHERE occurred_at < now() - interval '2 years'`.
- **PII:** the diff captures old+new values. If a field is sensitive, add it to
  a `_REDACT = {"password_hash", ...}` set in `_diff`/`_snapshot`.
- **Raw SQL bypasses ORM events.** `session.execute(update(Auction)...)` won't
  be audited. This codebase always mutates via ORM objects, so that's fine —
  make it a convention (or add option C's trigger as a belt-and-braces safety
  net on truly critical tables).
- **Testing:** one integration test that creates/updates/deletes an auction and
  asserts three audit rows with the right actor is enough to protect the layer.
