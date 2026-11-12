"""Settings loaded from environment variables via pydantic-settings.

Secure by default (skills/secure-config-supply-chain T2349/T62/T175):
* `APP_ENV` defaults to `production`: interactive docs off, HTTPS-only service URLs and origins.
  Development relaxations require an explicit `APP_ENV=development`.
* Secrets (service role key, JWT secret, database DSN) come only from the environment, have no
  defaults, are held as `SecretStr` (never in reprs/logs) and must not be empty or placeholders.
* The database DSN must use TLS with full certificate and host-name verification
  (`sslmode=verify-full`); `require` (no certificate check) is rejected.
See docs/security/secure-config.md for every setting, its default and its security impact.
"""

from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class Settings(BaseSettings):
    # `.env` is git-ignored and meant for local development only; Vercel injects real environment variables.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["production", "development", "test"] = "production"
    # Interactive API docs; honoured only outside production (never exposed in production).
    enable_docs: bool = False

    supabase_url: AnyHttpUrl
    supabase_anon_key: SecretStr
    supabase_service_role_key: SecretStr
    supabase_jwt_secret: SecretStr
    supabase_jwt_audience: str = "authenticated"

    database_url: SecretStr
    cors_allowed_origins: Annotated[list[AnyHttpUrl], NoDecode] = Field(default_factory=list)

    max_request_bytes: int = Field(1_048_576, ge=1024, le=10_485_760)
    max_upload_bytes: int = Field(5_242_880, ge=1024, le=52_428_800)
    rate_limit_per_minute: int = Field(120, ge=1, le=10_000)
    auth_rate_limit_per_minute: int = Field(10, ge=1, le=1_000)
    max_page_size: int = Field(100, ge=1, le=1_000)

    # Optional key material (SecretStr, never logged). Unset => derived from SUPABASE_JWT_SECRET via HKDF
    # (app/services/integrity.py); production deployments should set dedicated keys.
    audit_signing_key: SecretStr | None = None      # PEM, EC P-521 private key (audit record signatures)
    config_integrity_key: SecretStr | None = None   # HMAC key for alarm-limit / simulation-state integrity MACs

    # Host header allow-list (exact names or "*.suffix"); empty => middleware default (*.vercel.app, localhost).
    allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [v.strip().lower() for v in value.split(",") if v.strip()]
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @field_validator("supabase_anon_key", "supabase_service_role_key", "supabase_jwt_secret", "database_url")
    @classmethod
    def _not_empty_or_placeholder(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value().strip()
        if not raw or ("<" in raw and ">" in raw):  # e.g. "<service-role-key>" copied from .env.example
            raise ValueError("must be set from the environment (empty or placeholder value)")
        return value

    @field_validator("database_url")
    @classmethod
    def _require_tls(cls, value: SecretStr) -> SecretStr:
        modes = parse_qs(urlsplit(value.get_secret_value()).query).get("sslmode", [])
        if modes != ["verify-full"]:
            raise ValueError("DATABASE_URL must enforce TLS with certificate verification (sslmode=verify-full)")
        return value

    @model_validator(mode="after")
    def _https_outside_local_development(self) -> "Settings":
        def insecure(url: AnyHttpUrl) -> bool:
            local_dev = self.app_env == "development" and (url.host or "") in _LOCAL_HOSTS
            return url.scheme != "https" and not local_dev

        if insecure(self.supabase_url):
            raise ValueError("SUPABASE_URL must use https://")
        bad = [str(o) for o in self.cors_allowed_origins if insecure(o)]
        if bad:
            raise ValueError("CORS_ALLOWED_ORIGINS must use https:// origins")
        return self

    @model_validator(mode="after")
    def _production_secret_strength(self) -> "Settings":
        """Production refuses weak/placeholder system credentials and a superuser / non-TLS database DSN."""
        if not self.is_production:
            return self
        from app.services.passwords import database_url_problems, system_secret_problems

        problems = database_url_problems(self.database_url.get_secret_value())
        problems += system_secret_problems("SUPABASE_SERVICE_ROLE_KEY", self.supabase_service_role_key.get_secret_value())
        problems += system_secret_problems("SUPABASE_JWT_SECRET", self.supabase_jwt_secret.get_secret_value(), min_length=32)
        if self.config_integrity_key is not None and self.config_integrity_key.get_secret_value():
            problems += system_secret_problems("CONFIG_INTEGRITY_KEY", self.config_integrity_key.get_secret_value(),
                                               min_length=32)
        if problems:
            raise ValueError("insecure production configuration: " + "; ".join(problems))
        return self


    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def docs_enabled(self) -> bool:
        """Docs are off in production regardless of ENABLE_DOCS; elsewhere they need APP_ENV=development or ENABLE_DOCS."""
        return not self.is_production and (self.app_env == "development" or self.enable_docs)

    @property
    def origins(self) -> list[str]:
        return [str(o).rstrip("/") for o in self.cors_allowed_origins]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
