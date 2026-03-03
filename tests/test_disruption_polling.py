import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data.db_models import Base, Mode, Line, Station, StationNaptan, Disruption, DisruptedStop
from commands.disruption_polling import DisruptionPollingCommand


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
    db_session.add(Line(id="central", name="Central", mode_name="tube"))
    db_session.add(Station(id="sta_a", name="Aldgate", lat=51.5, lon=-0.07))
    db_session.add(StationNaptan(station_id="sta_a", naptan_code="940GZZLUALD"))
    db_session.commit()
    yield db_session


def make_delay(disruption_id="d1", line_id="central", affected_stops=None):
    from data.models import Delay
    return Delay(
        id=disruption_id,
        line_id=line_id,
        type="lineStatus",
        category="Minor Delays",
        categoryDescription="6",
        summary="Track fault",
        description="Minor delays expected",
        additionalInfo="n/a",
        created="2026-03-01",
        lastUpdate="2026-03-01",
        mode="tube",
        affected_stops=affected_stops or [],
    )


class TestPollAndStoreDisruptions:
    def test_new_disruption_stored_in_db(self, seeded_session):
        delay = make_delay("new-d1", "central")
        with patch.object(DisruptionPollingCommand, "__init__", lambda self: None):
            cmd = DisruptionPollingCommand.__new__(DisruptionPollingCommand)
            cmd.tfl_client = MagicMock()
            cmd.logger = MagicMock()
            cmd.tfl_client.get_all_line_statuses.return_value = [delay]

            result = cmd.poll_and_store_disruptions(seeded_session)

        assert result["new"] == 1
        stored = seeded_session.query(Disruption).filter_by(id="new-d1").first()
        assert stored is not None
        assert stored.is_active is True

    def test_existing_disruption_updated_not_duplicated(self, seeded_session):
        seeded_session.add(Disruption(
            id="existing-d1", line_id="central", type="lineStatus",
            category="Good Service", category_description="10",
            summary="Old summary", description="Old", additional_info="n/a",
            created="2026-01-01", last_update="2026-01-01", is_active=True
        ))
        seeded_session.commit()
        delay = make_delay("existing-d1", "central")
        delay.summary = "Updated summary"
        with patch.object(DisruptionPollingCommand, "__init__", lambda self: None):
            cmd = DisruptionPollingCommand.__new__(DisruptionPollingCommand)
            cmd.tfl_client = MagicMock()
            cmd.logger = MagicMock()
            cmd.tfl_client.get_all_line_statuses.return_value = [delay]

            result = cmd.poll_and_store_disruptions(seeded_session)

        assert result["updated"] == 1
        count = seeded_session.query(Disruption).filter_by(id="existing-d1").count()
        assert count == 1
        stored = seeded_session.query(Disruption).filter_by(id="existing-d1").first()
        assert stored.summary == "Updated summary"

    def test_absent_disruption_marked_inactive(self, seeded_session):
        seeded_session.add(Disruption(
            id="old-disruption", line_id="central", type="lineStatus",
            category="Minor Delays", category_description="6",
            summary="Old", description="Old", additional_info="n/a",
            created="2026-01-01", last_update="2026-01-01", is_active=True
        ))
        seeded_session.commit()
        with patch.object(DisruptionPollingCommand, "__init__", lambda self: None):
            cmd = DisruptionPollingCommand.__new__(DisruptionPollingCommand)
            cmd.tfl_client = MagicMock()
            cmd.logger = MagicMock()
            cmd.tfl_client.get_all_line_statuses.return_value = []

            result = cmd.poll_and_store_disruptions(seeded_session)

        assert result["resolved"] == 1
        stored = seeded_session.query(Disruption).filter_by(id="old-disruption").first()
        assert stored.is_active is False

    def test_stop_linked_by_station_id(self, seeded_session):
        delay = make_delay("d-with-stop", "central", affected_stops=["sta_a"])
        with patch.object(DisruptionPollingCommand, "__init__", lambda self: None):
            cmd = DisruptionPollingCommand.__new__(DisruptionPollingCommand)
            cmd.tfl_client = MagicMock()
            cmd.logger = MagicMock()
            cmd.tfl_client.get_all_line_statuses.return_value = [delay]

            cmd.poll_and_store_disruptions(seeded_session)

        disrupted_stop = seeded_session.query(DisruptedStop).filter_by(disruption_id="d-with-stop").first()
        assert disrupted_stop is not None
        assert disrupted_stop.station_id == "sta_a"

    def test_stop_linked_via_naptan_fallback(self, seeded_session):
        delay = make_delay("d-naptan", "central", affected_stops=["940GZZLUALD"])
        with patch.object(DisruptionPollingCommand, "__init__", lambda self: None):
            cmd = DisruptionPollingCommand.__new__(DisruptionPollingCommand)
            cmd.tfl_client = MagicMock()
            cmd.logger = MagicMock()
            cmd.tfl_client.get_all_line_statuses.return_value = [delay]

            cmd.poll_and_store_disruptions(seeded_session)

        disrupted_stop = seeded_session.query(DisruptedStop).filter_by(disruption_id="d-naptan").first()
        assert disrupted_stop is not None
        assert disrupted_stop.station_id == "sta_a"

    def test_exception_triggers_rollback_and_re_raises(self, seeded_session):
        with patch.object(DisruptionPollingCommand, "__init__", lambda self: None):
            cmd = DisruptionPollingCommand.__new__(DisruptionPollingCommand)
            cmd.tfl_client = MagicMock()
            cmd.logger = MagicMock()
            cmd.tfl_client.get_all_line_statuses.side_effect = RuntimeError("API down")

            with pytest.raises(RuntimeError, match="API down"):
                cmd.poll_and_store_disruptions(seeded_session)
