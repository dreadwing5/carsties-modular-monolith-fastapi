# Azure Integration: Function Apps, Cosmos DB, Blob Storage

How serverless compute and Azure storage services plug into the modular
monolith **without breaking its rules**: modules keep their boundaries, all
cross-module traffic stays events-or-contracts, and every cloud client lives
in some module's `infrastructure/` layer.

## 0. The placement rule

Before any Azure specifics, the one rule that keeps this clean:

> A cloud service is an *infrastructure detail of exactly one module* (a blob
> container the auctions module writes to), or an *external consumer of
> integration events* (a Function App reacting to `AuctionCreated`). It is
> never a shared back-channel between modules.

If two modules would talk through the same container/queue/collection, that's
a module boundary violation with extra steps — use the event bus.

---

## 1. Function Apps

A Function App is a **second deployable** next to the monolith. Good fits
here:

- scheduled work that shouldn't share the API's lifecycle — e.g. an
  every-minute *"mark auctions past `auction_end` as finished"* sweep
- bursty/slow work you don't want on the request path — image processing,
  email/notification fan-out
- webhooks from third parties that you'd rather keep off the main app

### Getting events out of the monolith

The outbox → in-process bus pipeline stays exactly as is. To let *external*
compute react, subscribe one more consumer that forwards contract events to an
Azure Service Bus topic — the same chokepoint trick as the audit layer:

```python
# shared/azure_bus.py
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage

async def forward_to_service_bus(event) -> None:
    async with _client() as client:  # cache the client in practice
        sender = client.get_topic_sender(topic_name="carsties-events")
        await sender.send_messages(
            ServiceBusMessage(
                event.model_dump_json(),
                subject=type(event).__name__,        # consumers filter on this
                content_type="application/json",
            )
        )
```

```python
# main.py lifespan — one line per event type, no module code touched
for event_type in (AuctionCreated, AuctionUpdated, AuctionDeleted):
    event_bus.subscribe(event_type, forward_to_service_bus, retries=5, retry_delay=2.0)
```

Because delivery already rides the outbox (at-least-once), the Function App
must be **idempotent** — same requirement the search consumer already meets
with its upserts.

### The Function App itself (Python v2 model)

```python
# function_app.py — its own repo/deployable, NOT inside src/carsties
import json
import azure.functions as func

app = func.FunctionApp()

@app.service_bus_topic_trigger(
    arg_name="msg", topic_name="carsties-events",
    subscription_name="notifications", connection="SERVICEBUS_CONNECTION",
)
def on_event(msg: func.ServiceBusMessage) -> None:
    event = json.loads(msg.get_body())
    if msg.subject == "AuctionCreated":
        ...  # send email, resize image, etc.

@app.timer_trigger(schedule="0 * * * * *", arg_name="timer")  # every minute
def finish_auctions(timer: func.TimerRequest) -> None:
    ...  # call the monolith's API, or write to a queue it consumes
```

### Getting results back in

The function talks back the same way any outside client does — **through the
front door**: call the public API with a service-account token from Keycloak
(client-credentials flow), or drop a message on a queue the monolith polls.
Never let it write to the app's Postgres directly; that bypasses the outbox,
the audit layer, and the module boundary all at once.

---

## 2. Cosmos DB

Two routes, in order of effort:

### a. Drop-in behind the search module (Cosmos DB for MongoDB)

`modules/search/infrastructure` talks to Mongo via `pymongo`. Cosmos DB's
MongoDB-compatible API means the read model can move to Cosmos with **zero
code changes**:

```bash
CARSTIES_MONGODB_URL="mongodb+srv://...cosmos.azure.com/..."
CARSTIES_MONGODB_DATABASE=search_db
```

Caveats to verify against your tier: `$text` index support (the search module
creates one in `search/infrastructure/db.py` — supported on vCore, limited on
RU-based), and RU throttling behaving differently from Mongo under load.

### b. Native Cosmos (SQL API) as a module's store

If a future module wants Cosmos natively, the shape mirrors the search
module: an async client in `infrastructure/db.py`, data-access functions in
`infrastructure/repository.py`, nothing above the infrastructure layer knows.

```python
# modules/<module>/infrastructure/db.py
from azure.cosmos.aio import CosmosClient

_client = CosmosClient(url=settings.cosmos_url, credential=settings.cosmos_key)
container = _client.get_database_client("carsties").get_container_client("items")
```

Pick the **partition key** the way this project picks Postgres schemas: per
module, aligned with how the module queries (for a search-like read model,
`/id` or `/seller`). Cross-partition fan-out queries are where Cosmos bills
hurt.

---

## 3. Blob Storage

Today `image_url` on an auction is just a string pointing anywhere. To own the
images: the auctions module gets an upload endpoint, and blobs become part of
its infrastructure.

```python
# modules/auctions/infrastructure/blobs.py
from azure.storage.blob.aio import BlobServiceClient

async def upload_image(auction_id: UUID, data: bytes, content_type: str) -> str:
    service = BlobServiceClient.from_connection_string(settings.azure_storage_connection)
    blob = service.get_container_client("auction-images").get_blob_client(f"{auction_id}.jpg")
    await blob.upload_blob(data, overwrite=True, content_type=content_type)
    return blob.url
```

```python
# modules/auctions/api/router.py
@router.post("/{auction_id}/image")
async def upload_auction_image(
    session: Session, username: CurrentUsername, auction_id: UUID, file: UploadFile
) -> Response:
    ...  # service checks ownership (same NotAuctionSellerError rule),
         # uploads via infrastructure.blobs, saves the URL on the item
```

Practicalities:

- **Local dev:** add [Azurite](https://github.com/Azure/Azurite) to
  `docker-compose.yml` — the same SDK against `http://localhost:10000`:

  ```yaml
  azurite:
    image: mcr.microsoft.com/azure-storage/azurite
    ports:
      - 10000:10000
  ```

- **Private containers:** store the blob *name*, not the URL, and serve
  short-lived SAS URLs from the API when a client asks.
- **Heavy processing** (thumbnails, EXIF stripping) is exactly the Function
  App case from §1 — a `blob_trigger` function reacts to the upload, writes
  derived blobs, done. The monolith never blocks on it.

---

## 4. Settings

All of it configures like everything else — typed fields in
`shared/settings.py`, `CARSTIES_`-prefixed env vars, defaults that work
against local emulators:

```python
service_bus_connection: str = ""          # empty = forwarding disabled
azure_storage_connection: str = "UseDevelopmentStorage=true"   # Azurite
```

Guard optional integrations on their setting (skip subscribing
`forward_to_service_bus` when the connection string is empty) so local dev
needs none of them.
