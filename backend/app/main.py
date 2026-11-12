"""FastAPI application factory.

Registers routers, CORS (explicit allow-list from settings), security-header / body-size /
rate-limit middleware and global exception handlers. Secure defaults (T2349): interactive API docs
and the OpenAPI schema exist only with APP_ENV=development (or ENABLE_DOCS outside production), debug is
always off, CORS allows only the configured exact origins, and a production start-up refuses to serve if
any route lacks authentication/authorization (deny by default).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from app.core.security import assert_routes_protected
from app.routers import (alarms, auth, break_glass, csp_report, events, files, maintenance, monitors, observations, patients,
                         profile, reports, settings as settings_router, simulation, staff, thresholds, wards)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if get_settings().is_production:
        assert_routes_protected(app, production=True)  # fail closed: never serve an unprotected route
    await db.open_pool()
    try:
        yield
    finally:
        await db.close_pool()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.is_production)
    app = FastAPI(
        title="ACME Clinical API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        debug=False,
    )
    install_error_handlers(app)

    # Order: outermost first in execution = last added.
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute,
                       auth_per_minute=settings.auth_rate_limit_per_minute)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,  # never "*": exact SPA origins only
        allow_credentials=False,          # bearer tokens, no cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        # WWW-Authenticate carries the step_up_required / session_* reasons the SPA reacts to.
        expose_headers=["X-Request-Id", "WWW-Authenticate", "Retry-After"],
        max_age=600,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes, upload_max_bytes=settings.max_upload_bytes)
    app.add_middleware(SecurityHeadersMiddleware, allowed_hosts=settings.allowed_hosts or None)

    for module in (auth, profile, wards, patients, observations, alarms, thresholds, monitors, maintenance, staff,
                   settings_router, simulation, events, reports, break_glass, files, csp_report):
        app.include_router(module.router)

    @app.get("/v1/health", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok"}

    # Deny by default at build time in every environment (docs routes tolerated outside production);
    # the lifespan re-checks in production before serving.
    assert_routes_protected(app, production=settings.is_production)
    return app



app = create_app()
