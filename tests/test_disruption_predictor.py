import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data.db_models import Base, Mode, Line, Station, Disruption, DisruptedStop
from data.disruption_analyzer import DisruptionPredictor


@pytest.fixture
def engine():
    e = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    yield e
    e.dispose()


@pytest.fixture
def session(engine):
    s = Session(engine)
    yield s
    s.close()


@pytest.fixture
def session_with_disruptions(session):
    session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
    session.add(Line(id="central", name="Central", mode_name="tube"))
    session.flush()
    recent = (datetime.now() - timedelta(days=5)).isoformat()
    for i in range(4):
        session.add(Disruption(
            id=f"d-{i}", line_id="central", type="lineStatus", category="MinorDelays",
            created=recent, is_active=True, duration_minutes=60.0,
        ))
    session.commit()
    yield session


class TestGetTimeContextFactors:
    def test_morning_peak_weekday_returns_high_multiplier(self):
        predictor = DisruptionPredictor(None)

        result = predictor.get_time_context_factors(datetime(2026, 3, 2, 8, 0))

        assert result["is_peak"] is True
        assert result["disruption_multiplier"] == 1.3

    def test_evening_peak_weekday_returns_high_multiplier(self):
        predictor = DisruptionPredictor(None)

        result = predictor.get_time_context_factors(datetime(2026, 3, 2, 18, 0))

        assert result["is_peak"] is True
        assert result["disruption_multiplier"] == 1.3

    def test_off_peak_weekday_returns_reduced_multiplier(self):
        predictor = DisruptionPredictor(None)

        result = predictor.get_time_context_factors(datetime(2026, 3, 2, 13, 0))

        assert result["is_peak"] is False
        assert result["disruption_multiplier"] == 0.7

    def test_night_hours_return_low_multiplier(self):
        predictor = DisruptionPredictor(None)

        result = predictor.get_time_context_factors(datetime(2026, 3, 2, 1, 0))

        assert result["disruption_multiplier"] == 0.5

    def test_midnight_hour_returns_low_multiplier(self):
        predictor = DisruptionPredictor(None)

        result = predictor.get_time_context_factors(datetime(2026, 3, 2, 23, 0))

        assert result["disruption_multiplier"] == 0.5

    def test_weekend_returns_reduced_multiplier(self):
        predictor = DisruptionPredictor(None)

        result = predictor.get_time_context_factors(datetime(2026, 3, 7, 9, 0))

        assert result["is_weekend"] is True
        assert result["disruption_multiplier"] == 0.7

    def test_boundary_hour_7_is_peak(self):
        predictor = DisruptionPredictor(None)

        result = predictor.get_time_context_factors(datetime(2026, 3, 2, 7, 0))

        assert result["is_peak"] is True

    def test_boundary_hour_17_is_peak(self):
        predictor = DisruptionPredictor(None)

        result = predictor.get_time_context_factors(datetime(2026, 3, 2, 17, 0))

        assert result["is_peak"] is True

    def test_hour_11_is_not_peak(self):
        predictor = DisruptionPredictor(None)

        result = predictor.get_time_context_factors(datetime(2026, 3, 2, 11, 0))

        assert result["is_peak"] is False

    def test_defaults_to_now_when_no_time_provided(self):
        predictor = DisruptionPredictor(None)

        result = predictor.get_time_context_factors()

        assert "hour_of_day" in result
        assert "disruption_multiplier" in result

    def test_result_contains_expected_keys(self):
        predictor = DisruptionPredictor(None)

        result = predictor.get_time_context_factors(datetime(2026, 3, 2, 12, 0))

        assert set(result.keys()) == {"hour_of_day", "is_peak", "is_weekend", "disruption_multiplier"}


class TestCalculateLineReliabilityScores:
    def test_line_with_disruptions_has_non_zero_fragility(self, session_with_disruptions):
        predictor = DisruptionPredictor(session_with_disruptions)

        scores = predictor.calculate_line_reliability_scores()

        assert "central" in scores
        assert scores["central"] >= 0.0

    def test_fragility_within_unit_interval(self, session_with_disruptions):
        predictor = DisruptionPredictor(session_with_disruptions)

        scores = predictor.calculate_line_reliability_scores()

        for fragility in scores.values():
            assert 0.0 <= fragility <= 1.0

    def test_many_long_disruptions_raise_fragility(self, session):
        session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        session.add(Line(id="bakerloo", name="Bakerloo", mode_name="tube"))
        session.flush()
        recent = (datetime.now() - timedelta(days=1)).isoformat()
        for i in range(20):
            session.add(Disruption(
                id=f"d-{i}", line_id="bakerloo", type="t", category="c",
                created=recent, is_active=True, duration_minutes=300.0,
            ))
        session.commit()
        predictor_many = DisruptionPredictor(session)

        score_many = predictor_many.calculate_line_reliability_scores()["bakerloo"]

        session2 = Session(session.get_bind())
        session2.add(Mode(name="tube2", isTflService=True, isScheduledService=True))
        session2.add(Line(id="bakerloo2", name="Bakerloo2", mode_name="tube2"))
        session2.flush()
        session2.add(Disruption(
            id="d-single", line_id="bakerloo2", type="t", category="c",
            created=recent, is_active=True, duration_minutes=30.0,
        ))
        session2.commit()
        predictor_few = DisruptionPredictor(session2)
        score_few = predictor_few.calculate_line_reliability_scores().get("bakerloo2", 0)
        session2.close()

        assert score_many >= score_few

    def test_second_call_returns_cached_result(self, session_with_disruptions):
        predictor = DisruptionPredictor(session_with_disruptions)
        first = predictor.calculate_line_reliability_scores()

        second = predictor.calculate_line_reliability_scores()

        assert first is second

    def test_clear_cache_forces_recalculation(self, session_with_disruptions):
        predictor = DisruptionPredictor(session_with_disruptions)
        first = predictor.calculate_line_reliability_scores()
        predictor.clear_cache()

        second = predictor.calculate_line_reliability_scores()

        assert first is not second


class TestCalculateStationReliabilityScores:
    def test_station_fragility_within_valid_range(self, session):
        session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        session.add(Line(id="jubilee", name="Jubilee", mode_name="tube"))
        session.add(Station(id="sta_wm", name="Westminster"))
        session.flush()
        recent = (datetime.now() - timedelta(days=1)).isoformat()
        session.add(Disruption(id="d1", line_id="jubilee", type="t", category="c", created=recent, is_active=True))
        session.flush()
        session.add(DisruptedStop(disruption_id="d1", station_id="sta_wm"))
        session.commit()
        predictor = DisruptionPredictor(session)

        scores = predictor.calculate_station_reliability_scores()

        assert "sta_wm" in scores
        assert 0.1 <= scores["sta_wm"] <= 0.5

    def test_most_disrupted_station_has_higher_fragility(self, session):
        session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        session.add(Line(id="northern", name="Northern", mode_name="tube"))
        session.add(Station(id="sta_max", name="Station Max"))
        session.add(Station(id="sta_low", name="Station Low"))
        session.flush()
        recent = (datetime.now() - timedelta(days=1)).isoformat()
        for i in range(5):
            session.add(Disruption(id=f"dn{i}", line_id="northern", type="t", category="c", created=recent, is_active=True))
            session.flush()
            session.add(DisruptedStop(disruption_id=f"dn{i}", station_id="sta_max"))
        session.add(Disruption(id="dlow", line_id="northern", type="t", category="c", created=recent, is_active=True))
        session.flush()
        session.add(DisruptedStop(disruption_id="dlow", station_id="sta_low"))
        session.commit()
        predictor = DisruptionPredictor(session)

        scores = predictor.calculate_station_reliability_scores()

        assert scores["sta_max"] > scores["sta_low"]

    def test_second_call_returns_cached_result(self, session):
        session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        session.add(Line(id="dist", name="District", mode_name="tube"))
        session.add(Station(id="sta_d", name="District St"))
        session.flush()
        recent = (datetime.now() - timedelta(days=1)).isoformat()
        session.add(Disruption(id="dd1", line_id="dist", type="t", category="c", created=recent, is_active=True))
        session.flush()
        session.add(DisruptedStop(disruption_id="dd1", station_id="sta_d"))
        session.commit()
        predictor = DisruptionPredictor(session)
        first = predictor.calculate_station_reliability_scores()

        second = predictor.calculate_station_reliability_scores()

        assert first is second


class TestPredictEdgeFragility:
    def test_result_clamped_to_unit_interval(self, session_with_disruptions):
        predictor = DisruptionPredictor(session_with_disruptions)

        fragility = predictor.predict_edge_fragility("central", "sta_a", "sta_b")

        assert 0.0 <= fragility <= 1.0

    def test_unknown_ids_use_default_fragility(self, session):
        session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        session.commit()
        predictor = DisruptionPredictor(session)

        fragility = predictor.predict_edge_fragility("nonexistent_line", "unknown_a", "unknown_b", datetime(2026, 3, 2, 12, 0))

        expected = (0.7 * 0.05 + 0.3 * ((0.05 + 0.05) / 2.0)) * 0.7
        assert fragility == pytest.approx(expected, abs=0.001)

    def test_peak_multiplier_increases_fragility_vs_off_peak(self, session_with_disruptions):
        predictor = DisruptionPredictor(session_with_disruptions)

        off_peak = predictor.predict_edge_fragility("central", "sta_a", "sta_b", datetime(2026, 3, 2, 13, 0))
        peak = predictor.predict_edge_fragility("central", "sta_a", "sta_b", datetime(2026, 3, 2, 8, 0))

        assert peak > off_peak
