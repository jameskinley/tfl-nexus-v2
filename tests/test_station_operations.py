import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data.db_models import Base, Mode, Line, Station, StationNaptan
from commands.station_operations import StationOperationsCommand


@pytest.fixture
def engine():
    e = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    yield e
    e.dispose()


@pytest.fixture
def db_session(engine):
    s = Session(engine)
    yield s
    s.close()


@pytest.fixture
def seeded_session(db_session):
    db_session.add(Station(id="sta_ald", name="Aldgate", lat=51.5, lon=-0.07))
    db_session.add(Station(id="sta_bnk", name="Bank", lat=51.51, lon=-0.088))
    db_session.add(Station(id="sta_chl", name="Chancery Lane", lat=51.52, lon=-0.11))
    db_session.commit()
    yield db_session


class TestSearchStationsValidation:
    def test_limit_zero_raises_400(self, db_session):
        cmd = StationOperationsCommand(db_session)

        with pytest.raises(HTTPException) as exc_info:
            cmd.search_stations("tube", limit=0)

        assert exc_info.value.status_code == 400

    def test_limit_101_raises_400(self, db_session):
        cmd = StationOperationsCommand(db_session)

        with pytest.raises(HTTPException) as exc_info:
            cmd.search_stations("tube", limit=101)

        assert exc_info.value.status_code == 400

    def test_limit_negative_raises_400(self, db_session):
        cmd = StationOperationsCommand(db_session)

        with pytest.raises(HTTPException) as exc_info:
            cmd.search_stations("tube", limit=-1)

        assert exc_info.value.status_code == 400

    def test_empty_query_raises_400(self, db_session):
        cmd = StationOperationsCommand(db_session)

        with pytest.raises(HTTPException) as exc_info:
            cmd.search_stations("", limit=10)

        assert exc_info.value.status_code == 400

    def test_whitespace_only_query_raises_400(self, db_session):
        cmd = StationOperationsCommand(db_session)

        with pytest.raises(HTTPException) as exc_info:
            cmd.search_stations("   ", limit=10)

        assert exc_info.value.status_code == 400

    def test_limit_100_is_valid(self, seeded_session):
        cmd = StationOperationsCommand(seeded_session)

        result = cmd.search_stations("Aldgate", limit=100)

        assert "stations" in result

    def test_results_contain_matching_stations(self, seeded_session):
        cmd = StationOperationsCommand(seeded_session)

        result = cmd.search_stations("Aldgate")

        names = [s.name for s in result["stations"]]
        assert "Aldgate" in names

    def test_count_matches_stations_length(self, seeded_session):
        cmd = StationOperationsCommand(seeded_session)

        result = cmd.search_stations("a")

        assert result["count"] == len(result["stations"])

    def test_limit_restricts_result_count(self, seeded_session):
        cmd = StationOperationsCommand(seeded_session)

        result = cmd.search_stations("a", limit=1)

        assert len(result["stations"]) <= 1


class TestFindClosestStation:
    def test_exact_match_returns_station(self, seeded_session):
        cmd = StationOperationsCommand(seeded_session)

        result = cmd.find_closest_station("Aldgate")

        assert result is not None
        assert result.name == "Aldgate"

    def test_fuzzy_match_returns_closest(self, seeded_session):
        cmd = StationOperationsCommand(seeded_session)

        result = cmd.find_closest_station("Bank Street", cutoff=0.1)

        assert result is not None
        assert "Bank" in result.name

    def test_no_match_returns_none(self, seeded_session):
        cmd = StationOperationsCommand(seeded_session)

        result = cmd.find_closest_station("zzzzcompletely_unrelated", cutoff=0.9)

        assert result is None

    def test_empty_db_returns_none(self, db_session):
        cmd = StationOperationsCommand(db_session)

        result = cmd.find_closest_station("Aldgate")

        assert result is None
