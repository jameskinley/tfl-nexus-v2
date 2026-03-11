"""
Tests for src/security.py.

Covers:
  - Hashing helpers
  - Key creation / verification / revocation
  - require_api_key FastAPI dependency (401, 429, 200)
  - require_admin_key FastAPI dependency (403, 200)
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from data.db_models import Base, APIKey
from security import (
    hash_api_key,
    verify_api_key,
    create_api_key,
    require_api_key,
    require_admin_key,
    _check_rate_limit,
    _request_log,
    _RATE_LIMIT,
)


# ── Shared in-memory DB fixture ───────────────────────────────────────────────

@pytest.fixture
def sec_engine():
    e = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(e)
    yield e
    e.dispose()


@pytest.fixture
def sec_db(sec_engine):
    session = Session(sec_engine)
    yield session
    session.close()


# ── hash_api_key ──────────────────────────────────────────────────────────────

def test_hash_api_key_deterministic():
    assert hash_api_key("mysecret") == hash_api_key("mysecret")


def test_hash_api_key_different_inputs():
    assert hash_api_key("key-a") != hash_api_key("key-b")


def test_hash_api_key_is_hex_string():
    h = hash_api_key("test")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ── verify_api_key ────────────────────────────────────────────────────────────

def test_verify_api_key_valid(sec_db):
    raw, _ = create_api_key("valid-test", sec_db)
    result = verify_api_key(raw, sec_db)
    assert result is not None
    assert result.name == "valid-test" #type: ignore


def test_verify_api_key_invalid(sec_db):
    assert verify_api_key("totally-wrong-key", sec_db) is None


def test_verify_api_key_revoked(sec_db):
    raw, record = create_api_key("revoke-test", sec_db)
    record.is_active = False #type: ignore
    sec_db.commit()
    assert verify_api_key(raw, sec_db) is None


# ── create_api_key ────────────────────────────────────────────────────────────

def test_create_api_key_stores_hash(sec_db):
    raw, record = create_api_key("store-test", sec_db)
    assert record.key_hash == hash_api_key(raw) #type: ignore


def test_create_api_key_admin_flag(sec_db):
    _, record = create_api_key("admin-test", sec_db, is_admin=True)
    assert record.is_admin is True


def test_create_api_key_default_not_admin(sec_db):
    _, record = create_api_key("regular-test", sec_db)
    assert record.is_admin is False


def test_create_api_key_raw_verifies(sec_db):
    raw, _ = create_api_key("verify-test", sec_db)
    assert verify_api_key(raw, sec_db) is not None


# ── Rate limiting ─────────────────────────────────────────────────────────────

def test_rate_limit_allows_under_limit():
    bucket = "rate-test-allow"
    _request_log.pop(bucket, None)
    for _ in range(_RATE_LIMIT):
        assert _check_rate_limit(bucket) is True


def test_rate_limit_blocks_over_limit():
    bucket = "rate-test-block"
    _request_log.pop(bucket, None)
    for _ in range(_RATE_LIMIT):
        _check_rate_limit(bucket)
    assert _check_rate_limit(bucket) is False


# ── FastAPI dependency integration (require_api_key / require_admin_key) ──────

def _make_test_app(sec_engine) -> tuple[FastAPI, TestClient]:
    """
    Build a minimal FastAPI app whose DB session is wired to *sec_engine*.
    Both endpoints exercise the real `require_api_key` / `require_admin_key`
    dependencies — no mocking.
    """
    from fastapi import Depends, Security
    from data.database import get_db

    app = FastAPI()

    def override_get_db():
        db = Session(sec_engine)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    @app.get("/protected")
    async def protected(key: APIKey = Depends(require_api_key)):
        return {"name": key.name}

    @app.get("/admin")
    async def admin_only(key: APIKey = Depends(require_admin_key)):
        return {"name": key.name, "is_admin": key.is_admin}

    return app, TestClient(app, raise_server_exceptions=False)


def test_require_api_key_missing(sec_engine):
    _, client = _make_test_app(sec_engine)
    resp = client.get("/protected")
    assert resp.status_code == 401


def test_require_api_key_invalid(sec_engine):
    _, client = _make_test_app(sec_engine)
    resp = client.get("/protected", headers={"X-API-Key": "not-a-real-key"})
    assert resp.status_code == 401


def test_require_api_key_valid(sec_engine):
    app, client = _make_test_app(sec_engine)
    db = Session(sec_engine)
    raw, _ = create_api_key("dep-test", db)
    db.close()
    resp = client.get("/protected", headers={"X-API-Key": raw})
    assert resp.status_code == 200
    assert resp.json()["name"] == "dep-test"


def test_require_admin_key_non_admin(sec_engine):
    app, client = _make_test_app(sec_engine)
    db = Session(sec_engine)
    raw, _ = create_api_key("non-admin", db, is_admin=False)
    db.close()
    resp = client.get("/admin", headers={"X-API-Key": raw})
    assert resp.status_code == 403


def test_require_admin_key_admin(sec_engine):
    app, client = _make_test_app(sec_engine)
    db = Session(sec_engine)
    raw, _ = create_api_key("admin-dep-test", db, is_admin=True)
    db.close()
    resp = client.get("/admin", headers={"X-API-Key": raw})
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is True


def test_require_api_key_updates_request_count(sec_engine):
    app, client = _make_test_app(sec_engine)
    with Session(sec_engine) as db:
        raw, record = create_api_key("count-test", db)
        initial_count = record.request_count

    client.get("/protected", headers={"X-API-Key": raw})

    with Session(sec_engine) as db2:
        updated = db2.query(APIKey).filter(APIKey.key_hash == hash_api_key(raw)).first()
        assert updated.request_count == initial_count + 1 #type: ignore
