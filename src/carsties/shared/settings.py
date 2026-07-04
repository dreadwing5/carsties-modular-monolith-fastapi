"""Typed application settings loaded from env vars / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CARSTIES_")

    database_url: str = "postgresql+asyncpg://postgres:postgrespw@localhost:5433/auctions"
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "search_db"

    # The Keycloak realm acting as the OIDC authority.
    identity_server_url: str = "http://localhost:5001/realms/carsties"

    # How often the outbox poller dispatches pending events
    outbox_poll_interval_seconds: float = 10.0

    seed_database: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
