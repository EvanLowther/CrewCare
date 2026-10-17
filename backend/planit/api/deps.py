from fastapi import HTTPException

from planit.config import settings


def use_mock() -> bool:
    return settings.mock


def not_built(what: str) -> HTTPException:
    """Placeholder for endpoints whose database version isn't written yet. Run with PLANIT_MOCK=1 meanwhile."""
    return HTTPException(status_code=501, detail=f"{what}: database version not built yet (set PLANIT_MOCK=1)")
