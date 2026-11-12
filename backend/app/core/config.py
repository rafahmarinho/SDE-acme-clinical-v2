"""Settings loaded from environment variables via pydantic-settings.

Secrets (service role key, DB password, JWT secret) come only from the environment and are
held as SecretStr so they never appear in reprs or logs. Production is the secure default.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["production", "development", "test"] = "production"

    supabase_url: AnyHttpUrl
    supabase_anon_key: SecretStr
    supabase_service_role_key: SecretStr
    supabase_jwt_secret: SecretStr
    supabase_jwt_audience: str = "authenticated"

    database_url: SecretStr
    cors_allowed_origins: Annotated[list[AnyHttpUrl], NoDecode] = Field(default_factory=list)

    max_request_bytes: int = 1_048_576
    max_upload_bytes: int = 5_242_880
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10
    max_page_size: int = 100

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def _require_tls(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if "sslmode=verify-full" not in raw and "sslmode=require" not in raw:
            raise ValueError("DATABASE_URL must enforce TLS (sslmode=verify-full)")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def origins(self) -> list[str]:
        return [str(o).rstrip("/") for o in self.cors_allowed_origins]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
