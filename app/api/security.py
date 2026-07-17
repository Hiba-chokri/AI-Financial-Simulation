"""
API-key authentication.

Callers must send a valid key in the `X-API-Key` header. Attach `require_api_key`
as a dependency to any route that must be protected; `/health` stays open so
monitoring can reach it without a key.
"""
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core import config

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _key_is_valid(candidate: str) -> bool:
    """Constant-time comparison against every configured key (no timing leak)."""
    return any(secrets.compare_digest(candidate, key) for key in config.API_KEYS)


def require_api_key(api_key: str = Security(_api_key_header)) -> str:
    """FastAPI dependency: allow the request only if it carries a known key."""
    if not config.AUTH_ENABLED:
        return "auth-disabled"
    if api_key and _key_is_valid(api_key):
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key. Send it in the 'X-API-Key' header.",
        headers={"WWW-Authenticate": "API-Key"},
    )
