import os

os.environ["DATABASE_URL"] = "sqlite:///test_tfl.db"
for _var in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"):
    os.environ.pop(_var, None)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data.db_models import Base, Mode, Line, Station, StationNaptan, Disruption, DisruptedStop


@pytest.fixture
def engine():
    e = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    yield e
    e.dispose()


@pytest.fixture
def db_session(engine):
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def seeded_db_session(db_session):
    mode = Mode(name="tube", isTflService=True, isScheduledService=True)
    db_session.add(mode)

    line = Line(id="central", name="Central", mode_name="tube")
    db_session.add(line)

    station_a = Station(id="sta_a", name="Aldgate", lat=51.5, lon=-0.07)
    station_b = Station(id="sta_b", name="Bank", lat=51.51, lon=-0.088)
    station_c = Station(id="sta_c", name="Chancery Lane", lat=51.52, lon=-0.11)
    db_session.add_all([station_a, station_b, station_c])

    db_session.add(StationNaptan(station_id="sta_a", naptan_code="940GZZLUALD"))
    db_session.add(StationNaptan(station_id="sta_b", naptan_code="940GZZLUBNK"))

    db_session.commit()
    yield db_session


# ── Security fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def admin_key_raw(db_session):
    """Return the raw admin API key and persist the record to *db_session*."""
    from security import create_api_key
    raw, _ = create_api_key("test-admin", db_session, is_admin=True)
    return raw


@pytest.fixture
def admin_key_record(db_session, admin_key_raw):
    """Return the persisted ``APIKey`` record for the admin key."""
    from security import verify_api_key
    return verify_api_key(admin_key_raw, db_session)


@pytest.fixture
def regular_key_raw(db_session):
    """Return the raw regular (non-admin) API key."""
    from security import create_api_key
    raw, _ = create_api_key("test-regular", db_session, is_admin=False)
    return raw


@pytest.fixture
def regular_key_record(db_session, regular_key_raw):
    """Return the persisted ``APIKey`` record for the regular key."""
    from security import verify_api_key
    return verify_api_key(regular_key_raw, db_session)


@pytest.fixture
def admin_headers(admin_key_raw):
    return {"X-API-Key": admin_key_raw}


@pytest.fixture
def regular_headers(regular_key_raw):
    return {"X-API-Key": regular_key_raw}
