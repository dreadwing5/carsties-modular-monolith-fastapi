"""≈ AddAuthentication().AddJwtBearer() — validates JWTs issued by the external
OIDC provider (Keycloak, standing in for Duende IdentityServer).

`CurrentUsername` is the equivalent of the .NET `ICurrentUser` service plus the
`UserWithUsername` authorization policy: it 401s without a valid bearer token
and 403s if the token carries no username.
"""

from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from carsties.shared.settings import get_settings

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    authority = get_settings().identity_server_url
    return jwt.PyJWKClient(f"{authority}/protocol/openid-connect/certs")


def _decode(token: str) -> dict[str, Any]:
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=get_settings().identity_server_url,
        # ≈ TokenValidationParameters.ValidateAudience = false
        options={"verify_aud": False},
    )


def get_current_username(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = _decode(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # ≈ NameClaimType = "username"; Keycloak calls it preferred_username
    username = claims.get("preferred_username") or claims.get("username") or ""
    if not username.strip():
        # ≈ the UserWithUsername policy assertion failing -> Forbid
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return username


CurrentUsername = Annotated[str, Depends(get_current_username)]
