"""
Shared security layer for the REST API and MCP server.

Both surfaces authenticate callers using the same mechanism:
  - REST API  → `require_api_key` / `require_admin_key` FastAPI dependencies
  - MCP (SSE) → `ApiKeyMiddleware` Starlette ASGI middleware

All validation logic ultimately calls `verify_api_key`, so there is a
single source of truth for key lookup and rate-limiting.
"""

import hashlib
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from data.database import SessionLocal, get_db
from data.db_models import APIKey

# ── OpenAPI security scheme ───────────────────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ── Core helpers ──────────────────────────────────────────────────────────────

def hash_api_key(raw: str) -> str:
    """Return the SHA-256 hex digest of *raw*."""
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_api_key(raw: str, db: Session) -> APIKey | None:
    """Look up *raw* in the database; return the record or ``None``."""
    key_hash = hash_api_key(raw)
    return (
        db.query(APIKey)
        .filter(APIKey.key_hash == key_hash, APIKey.is_active == True)
        .first()
    )


def create_api_key(name: str, db: Session, is_admin: bool = False) -> tuple[str, APIKey]:
    """
    Generate a new API key, persist it, and return ``(raw_key, record)``.
    The raw key is returned only once — store it immediately.
    """
    raw = secrets.token_urlsafe(32)
    record = APIKey(
        key_hash=hash_api_key(raw),
        name=name,
        is_admin=is_admin,
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return raw, record


# ── Rate limiting (60 req / 60 s per key, in-memory sliding window) ───────────
_RATE_LIMIT = 60
_RATE_WINDOW = 60.0  # seconds
_request_log: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(bucket: str) -> bool:
    """
    Sliding-window rate check. Returns ``True`` if the request is allowed.
    Thread-safe for CPython's GIL; not distributed across multiple workers.
    """
    now = time.monotonic()
    window_start = now - _RATE_WINDOW
    log = _request_log[bucket]
    _request_log[bucket] = [t for t in log if t > window_start]
    if len(_request_log[bucket]) >= _RATE_LIMIT:
        return False
    _request_log[bucket].append(now)
    return True


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def require_api_key(
    raw_key: str | None = Security(_api_key_header),
    db: Session = Depends(get_db),
) -> APIKey:
    """
    Dependency that validates the ``X-API-Key`` header.
    Raises ``401`` if missing/invalid and ``429`` if rate-limited.
    """
    if not raw_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    record = verify_api_key(raw_key, db)
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    if not _check_rate_limit(raw_key):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Max 60 requests per minute.",
        )
    record.request_count += 1 #type: ignore
    record.last_used_at = datetime.now(timezone.utc) #type: ignore
    db.commit()
    return record


async def require_admin_key(key: APIKey = Depends(require_api_key)) -> APIKey:
    """
    Dependency that additionally requires ``is_admin=True``.
    Raises ``403`` for valid but non-admin keys.
    """
    if not key.is_admin: #type: ignore
        raise HTTPException(status_code=403, detail="Admin access required")
    return key


# ── MCP / blanket ASGI middleware ─────────────────────────────────────────────

class ApiKeyMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that validates ``X-API-Key`` on every request.
    Used by the MCP SSE server; mirrors the logic in ``require_api_key``.
    """

    async def dispatch(self, request: Request, call_next):
        raw_key = request.headers.get("x-api-key")
        if not raw_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API key"},
            )

        db = SessionLocal()
        try:
            record = verify_api_key(raw_key, db)
            if record is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or revoked API key"},
                )
            if not _check_rate_limit(raw_key):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Max 60 requests per minute."},
                )
            record.request_count += 1 #type: ignore
            record.last_used_at = datetime.now(timezone.utc) #type: ignore
            db.commit()
        finally:
            db.close()

        return await call_next(request)
