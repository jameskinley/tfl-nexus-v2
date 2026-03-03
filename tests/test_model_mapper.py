import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data.db_models import Base, Mode, Line, Station, StationNaptan, Route
from data.mapper import ModelMapper
from data import models as api


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


class TestTimeToMinutes:
    def test_none_returns_none(self):
        result = ModelMapper._time_to_minutes(None)

        assert result is None

    def test_empty_dict_returns_none(self):
        result = ModelMapper._time_to_minutes({})

        assert result is None

    def test_valid_hour_and_minute_converted_correctly(self):
        result = ModelMapper._time_to_minutes({"hour": "9", "minute": "30"})

        assert result == 570.0

    def test_midnight_returns_zero(self):
        result = ModelMapper._time_to_minutes({"hour": "0", "minute": "0"})

        assert result == 0.0

    def test_end_of_day_minutes_correct(self):
        result = ModelMapper._time_to_minutes({"hour": "23", "minute": "59"})

        assert result == 23 * 60 + 59

    def test_non_numeric_values_return_none(self):
        result = ModelMapper._time_to_minutes({"hour": "abc", "minute": "xyz"})

        assert result is None


class TestGetOrCreateStation:
    def test_cache_hit_returns_same_object_without_db_call(self, db_session):
        mapper = ModelMapper(session=db_session)
        station_a = mapper._get_or_create_station("Aldgate", "940GZZLUALD")

        station_b = mapper._get_or_create_station("Aldgate", "940GZZLUALD")

        assert station_a is station_b

    def test_naptan_db_lookup_returns_existing_station(self, db_session):
        existing = Station(id="sta_existing", name="Bank")
        db_session.add(existing)
        db_session.add(StationNaptan(station_id="sta_existing", naptan_code="940GZZLUBNK"))
        db_session.commit()
        mapper = ModelMapper(session=db_session)

        result = mapper._get_or_create_station("Bank", "940GZZLUBNK")

        assert result.id == "sta_existing"

    def test_name_db_lookup_returns_existing_station_when_no_naptan_match(self, db_session):
        existing = Station(id="sta_nm", name="Liverpool Street")
        db_session.add(existing)
        db_session.commit()
        mapper = ModelMapper(session=db_session)

        result = mapper._get_or_create_station("Liverpool Street", "UNKNOWN_NAPTAN")

        assert result.id == "sta_nm"

    def test_no_match_creates_new_station_with_warning(self, db_session):
        mapper = ModelMapper(session=db_session)

        result = mapper._get_or_create_station("Brand New Station", "NEW_NAPTAN")

        assert result.name == "Brand New Station"
        assert any(n.naptan_code == "NEW_NAPTAN" for n in result.naptans)

    def test_new_station_added_to_cache(self, db_session):
        mapper = ModelMapper(session=db_session)
        first = mapper._get_or_create_station("Ghost Station", "GHO_NAPTAN")

        second = mapper._get_or_create_station("Ghost Station", "GHO_NAPTAN")

        assert first is second


class TestApiModeToDb:
    def test_first_call_creates_mode(self):
        mapper = ModelMapper()
        mode = api.Mode(name="tube", isTflService=True, isScheduledService=True)

        result = mapper.api_mode_to_db(mode)

        assert result.name == "tube"

    def test_second_call_returns_cached_object(self):
        mapper = ModelMapper()
        mode = api.Mode(name="tube", isTflService=True, isScheduledService=True)
        first = mapper.api_mode_to_db(mode)

        second = mapper.api_mode_to_db(mode)

        assert first is second


class TestApiLineToDb:
    def test_second_call_for_same_id_returns_cached_object(self):
        mapper = ModelMapper()
        mode = api.Mode(name="tube", isTflService=True, isScheduledService=True)
        line = api.Line(id="central", name="Central", mode=mode, routes=[], disruptions=[])
        first = mapper.api_line_to_db(line, include_routes=False)

        second = mapper.api_line_to_db(line, include_routes=False)

        assert first is second


class TestDbRouteToApi:
    def test_intervals_sorted_ascending_by_ordinal(self, db_session):
        db_session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        db_session.add(Line(id="central", name="Central", mode_name="tube"))
        db_session.flush()
        route = Route(route_id="central-route", name="central-route", line_id="central")
        db_session.add(route)
        db_session.flush()

        sta_1 = Station(id="s1", name="Station One")
        sta_2 = Station(id="s2", name="Station Two")
        sta_3 = Station(id="s3", name="Station Three")
        db_session.add_all([sta_1, sta_2, sta_3])
        db_session.add(StationNaptan(station_id="s1", naptan_code="NAP1"))
        db_session.add(StationNaptan(station_id="s2", naptan_code="NAP2"))
        db_session.add(StationNaptan(station_id="s3", naptan_code="NAP3"))
        db_session.flush()

        from data.db_models import StationInterval
        db_session.add(StationInterval(route_id=route.id, station_id="s3", ordinal=3, time_to_arrival=10.0))
        db_session.add(StationInterval(route_id=route.id, station_id="s1", ordinal=1, time_to_arrival=0.0))
        db_session.add(StationInterval(route_id=route.id, station_id="s2", ordinal=2, time_to_arrival=5.0))
        db_session.commit()

        mapper = ModelMapper(session=db_session)

        result = mapper.db_route_to_api(route)

        ordinals = [node.ordinal for node in result.route]
        assert ordinals == sorted(ordinals)

    def test_interval_with_no_naptans_uses_empty_string(self, db_session):
        db_session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        db_session.add(Line(id="district", name="District", mode_name="tube"))
        db_session.flush()
        route = Route(route_id="district-route", name="district-route", line_id="district")
        db_session.add(route)
        db_session.flush()

        sta = Station(id="s_bare", name="Bare Station")
        db_session.add(sta)
        db_session.flush()

        from data.db_models import StationInterval
        db_session.add(StationInterval(route_id=route.id, station_id="s_bare", ordinal=1, time_to_arrival=0.0))
        db_session.commit()

        mapper = ModelMapper(session=db_session)

        result = mapper.db_route_to_api(route)

        assert result.route[0].stop_naptan == ""
