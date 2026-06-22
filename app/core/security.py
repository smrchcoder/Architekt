from __future__ import annotations

from hmac import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.config import settings


ADMIN_API_KEY_HEADER = "X-API-Key"


def require_admin_api_key(
    x_api_key: Annotated[str | None, Header(alias=ADMIN_API_KEY_HEADER)] = None,
) -> None:
    configured_api_key = settings.backend_api_key
    if not configured_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API access is unavailable",
        )

    if not x_api_key or not compare_digest(x_api_key, configured_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key",
        )
