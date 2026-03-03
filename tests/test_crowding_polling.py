import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data.db_models import Base, Mode, Line, Station, StationNaptan, StationCrowding, PollingMeta
from commands.crowding_polling import CrowdingPollingCommand


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
    db_session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
    db_session.add(Station(id="sta_a", name="Aldgate", lat=51.5, lon=-0.07))
    db_session.add(StationNaptan(station_id="sta_a", naptan_code="940GZZLUALD"))
    db_session.commit()
    yield db_session


class TestPollAndUpdateRateLimit:
    def test_skipped_when_polled_within_900_seconds(self, seeded_session):
        recent_time = (datetime.now() - timedelta(seconds=300)).isoformat()
        seeded_session.add(PollingMeta(
            poll_type="crowding",
            last_poll_timestamp=recent_time,
            poll_interval_seconds=900
        ))
        seeded_session.commit()

        with patch("commands.crowding_polling.TflClient"):
            cmd = CrowdingPollingCommand(seeded_session)

            result = cmd.poll_and_update()

        assert result.get("skipped") is True

    def test_not_skipped_when_poll_interval_exceeded(self, seeded_session):
        old_time = (datetime.now() - timedelta(seconds=1800)).isoformat()
        seeded_session.add(PollingMeta(
            poll_type="crowding",
            last_poll_timestamp=old_time,
            poll_interval_seconds=900
        ))
        seeded_session.commit()

        with patch("commands.crowding_polling.TflClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.get_stations_crowding.return_value = {}
            cmd = CrowdingPollingCommand(seeded_session)

            result = cmd.poll_and_update()

        assert result.get("skipped") is not True


class TestCapacityToLevelClassification:
    def test_very_low_crowding_classified_as_low(self, seeded_session):
        with patch("commands.crowding_polling.TflClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.get_stations_crowding.return_value = {
                "940GZZLUALD": {"crowding": 0.10, "timestamp": datetime.now().isoformat()}
            }
            cmd = CrowdingPollingCommand(seeded_session)

            cmd.poll_and_update()

        record = seeded_session.query(StationCrowding).filter_by(station_id="sta_a").first()
        assert record.crowding_level == "low"

    def test_boundary_25_percent_classified_as_low(self, seeded_session):
        with patch("commands.crowding_polling.TflClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.get_stations_crowding.return_value = {
                "940GZZLUALD": {"crowding": 0.25, "timestamp": datetime.now().isoformat()}
            }
            cmd = CrowdingPollingCommand(seeded_session)

            cmd.poll_and_update()

        record = seeded_session.query(StationCrowding).filter_by(station_id="sta_a").first()
        assert record.crowding_level == "low"

    def test_40_percent_classified_as_moderate(self, seeded_session):
        with patch("commands.crowding_polling.TflClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.get_stations_crowding.return_value = {
                "940GZZLUALD": {"crowding": 0.40, "timestamp": datetime.now().isoformat()}
            }
            cmd = CrowdingPollingCommand(seeded_session)

            cmd.poll_and_update()

        record = seeded_session.query(StationCrowding).filter_by(station_id="sta_a").first()
        assert record.crowding_level == "moderate"

    def test_60_percent_classified_as_high(self, seeded_session):
        with patch("commands.crowding_polling.TflClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.get_stations_crowding.return_value = {
                "940GZZLUALD": {"crowding": 0.60, "timestamp": datetime.now().isoformat()}
            }
            cmd = CrowdingPollingCommand(seeded_session)

            cmd.poll_and_update()

        record = seeded_session.query(StationCrowding).filter_by(station_id="sta_a").first()
        assert record.crowding_level == "high"

    def test_above_75_percent_classified_as_very_high(self, seeded_session):
        with patch("commands.crowding_polling.TflClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.get_stations_crowding.return_value = {
                "940GZZLUALD": {"crowding": 0.90, "timestamp": datetime.now().isoformat()}
            }
            cmd = CrowdingPollingCommand(seeded_session)

            cmd.poll_and_update()

        record = seeded_session.query(StationCrowding).filter_by(station_id="sta_a").first()
        assert record.crowding_level == "very_high"


class TestGetCrowdingSummary:
    def test_no_records_returns_zeros(self, db_session):
        with patch("commands.crowding_polling.TflClient"):
            cmd = CrowdingPollingCommand(db_session)

            result = cmd.get_crowding_summary()

        assert result["total_stations"] == 0
        assert result["high_crowding_count"] == 0
        assert result["average_capacity"] == 0.0

    def test_high_crowding_stations_counted_above_80_percent(self, db_session):
        db_session.add(Station(id="sta_hc", name="High Crowding Station"))
        db_session.add(Station(id="sta_lc", name="Low Crowding Station"))
        db_session.flush()
        now = datetime.now()
        db_session.add(StationCrowding(
            station_id="sta_hc", timestamp=now,
            crowding_level="very_high", capacity_percentage=90.0,
            time_slice="live", data_source="test"
        ))
        db_session.add(StationCrowding(
            station_id="sta_lc", timestamp=now,
            crowding_level="low", capacity_percentage=20.0,
            time_slice="live", data_source="test"
        ))
        db_session.commit()

        with patch("commands.crowding_polling.TflClient"):
            cmd = CrowdingPollingCommand(db_session)

            result = cmd.get_crowding_summary()

        assert result["high_crowding_count"] == 1

    def test_average_capacity_calculated_correctly(self, db_session):
        db_session.add(Station(id="sta_avg", name="Average Station"))
        db_session.flush()
        now = datetime.now()
        db_session.add(StationCrowding(
            station_id="sta_avg", timestamp=now,
            crowding_level="moderate", capacity_percentage=40.0,
            time_slice="live", data_source="test"
        ))
        db_session.add(StationCrowding(
            station_id="sta_avg", timestamp=now,
            crowding_level="high", capacity_percentage=60.0,
            time_slice="live", data_source="test"
        ))
        db_session.commit()

        with patch("commands.crowding_polling.TflClient"):
            cmd = CrowdingPollingCommand(db_session)

            result = cmd.get_crowding_summary()

        assert result["average_capacity"] == pytest.approx(50.0, abs=0.1)
