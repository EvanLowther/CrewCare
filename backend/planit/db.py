"""Shared Postgres connection pool (Tiger Data)."""

from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from planit.config import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not settings.database_url:
            raise RuntimeError("PLANIT_DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=5, kwargs={"row_factory": dict_row},
                               open=True)
    return _pool


@contextmanager
def connection():
    with get_pool().connection() as conn:
        yield conn


def check() -> str:
    """'connected', 'unavailable', or 'not_configured'."""
    if not settings.database_url:
        return "not_configured"
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        return "connected"
    except Exception:
        return "unavailable"
