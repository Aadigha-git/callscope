"""URL helpers for sync/async Postgres drivers."""

from __future__ import annotations


def to_async_url(url: str) -> str:
    """Convert ``postgresql://`` (or bare) URLs to SQLAlchemy async psycopg."""
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    raise ValueError(f"unsupported database URL scheme: {url!r}")


def to_sync_url(url: str) -> str:
    """Convert to a libpq/psycopg sync URL (no SQLAlchemy driver prefix)."""
    for prefix in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    if url.startswith(("postgresql://", "postgres://")):
        return url.replace("postgres://", "postgresql://", 1)
    raise ValueError(f"unsupported database URL scheme: {url!r}")
