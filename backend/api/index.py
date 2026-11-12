"""Vercel serverless entry point: exposes the ASGI app from app.main."""

from app.main import app

__all__ = ["app"]
