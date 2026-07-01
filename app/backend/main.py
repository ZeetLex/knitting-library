"""Compatibility entrypoint for Docker and existing uvicorn commands."""

from app.main import app

__all__ = ["app"]
