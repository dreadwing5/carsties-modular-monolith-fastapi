# Authorization & Policies: permission levels without scattering `if` checks

Authentication (who are you?) is already done — Keycloak issues JWTs and
`shared/auth.py` validates them. This doc covers **authorization** (what may
you do?): how the current rules work, and how to grow them into role- and
policy-based permission levels.

## 1. The three layers we already have

Authorization in this codebase is deliberately layered — each check lives at
the cheapest place that can make the decision:

| Layer | Where | Decides | Example |
|---|---|---|---|
| **Edge (gateway)** | `src/carsties/gateway.py` | "is a bearer token even present?" | `POST /auctions` without a token → 401 before any routing |
| **Endpoint (dependency)** | `shared/auth.py` → `CurrentUsername` | "is the token valid, and who is it?" | invalid signature → 401; no username claim → 403 |
| **Resource (service)** | `modules/auctions/application/service.py` | "may *this* user touch *this* row?" | `NotAuctionSellerError` when `auction.seller != username` → 403 |

The pattern to keep: **identity is resolved once at the endpoint; rules about
data live next to the data, in the service layer.** Routers translate policy
failures to status codes; they never contain the rule itself.

## 2. Adding permission levels (roles)

### a. Put roles in the token

Keycloak already sends realm roles in every access token:

```json
{
  "preferred_username": "bob",
  "realm_access": { "roles": ["seller", "admin"] }
}
```

Define the roles in `keycloak/` (realm export → `roles` section, assign to
users), and they appear in the JWT with no app-side session state. Adding a
role to a user requires no deploy.

### b. Resolve a `User`, not just a username

Extend `shared/auth.py` with a richer principal (keep `CurrentUsername`
delegating to it so existing endpoints don't change):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    username: str
    roles: frozenset[str]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    claims = _decode_or_401(credentials)          # same 401 handling as today
    username = claims.get("preferred_username") or ""
    if not username.strip():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    realm_roles = claims.get("realm_access", {}).get("roles", [])
    return User(username=username, roles=frozenset(realm_roles))


CurrentUser = Annotated[User, Depends(get_current_user)]
```

### c. Role requirements as dependencies (the "policy" unit)

A policy is just a dependency that either returns the user or raises 403 —
composable, testable, and visible in the OpenAPI docs:

```python
def require_roles(*required: str) -> Any:
    def check(user: CurrentUser) -> User:
        if not set(required) <= user.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return user

    return Depends(check)
```

Use it per endpoint, or for a whole router:

```python
@router.delete("/{auction_id}/force")
async def force_delete(admin: Annotated[User, require_roles("admin")], ...): ...

admin_router = APIRouter(prefix="/api/admin", dependencies=[require_roles("admin")])
```

### d. Resource policies stay in the service layer

Role checks answer "can this *kind* of user do this?" — ownership answers
"can this user do it *to this row*?". The second kind needs the data, so it
belongs where the data is loaded. Pass the `User` down and let the rule read
naturally:

```python
# modules/auctions/application/service.py
def _assert_can_modify(auction: Auction, user: User) -> None:
    if auction.seller != user.username and "admin" not in user.roles:
        raise NotAuctionSellerError
```

The router keeps doing what it does today: catch the domain error, return 403.

## 3. The resulting permission ladder

| Level | Granted by | Can |
|---|---|---|
| Anonymous | nothing | `GET /api/auctions`, `GET /api/search` |
| Authenticated | valid JWT with username | create auctions |
| Seller (owner) | ownership of the row | update/delete **their own** auctions |
| `admin` role | Keycloak role assignment | update/delete **any** auction, admin endpoints |

Notice the levels come from three different mechanisms (nothing / dependency /
service rule / role) — that's intentional. Don't force everything into roles:
"owner" is not a role, it's a relationship to a row.

## 4. Practicalities

- **Module boundaries hold.** `User`, `CurrentUser` and `require_roles` live in
  the shared kernel (`shared/auth.py`); modules already may import shared.
  Resource rules live inside each module — the auctions module's ownership
  rule is nobody else's business.
- **The gateway check stays coarse.** It only asserts a token is *present* on
  writes; don't teach it roles. Fine-grained decisions belong behind it, where
  the claims are actually validated.
- **Testing:** override the dependency, not the token machinery —
  `app.dependency_overrides[get_current_user] = lambda: User("bob", frozenset({"admin"}))`.
  One test per rung of the ladder (401 anonymous, 403 wrong user, 403 missing
  role, 200 owner, 200 admin) protects the whole scheme.
- **When rules outgrow this** (multi-tenant, delegation, "managers of the
  seller's org may edit"), reach for a policy engine ([Oso](https://www.osohq.com/),
  [Casbin](https://casbin.org/)) *inside the service layer* — the call sites
  don't change, only `_assert_can_modify`'s implementation does.
- **Never authorize on data the client sent.** The username and roles come
  from the verified token; DTO fields like `seller` are display data.
