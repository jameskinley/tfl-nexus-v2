import pytest
import networkx as nx
from datetime import datetime, time, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data.db_models import Base, Mode, Line, Station, Disruption, DisruptedStop
from graph.graph_manager import GraphManager


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
def simple_graph():
    gm = GraphManager()
    gm.graph.add_node("a", name="Alpha", lines=["central"], modes=["tube"])
    gm.graph.add_node("b", name="Beta", lines=["central"], modes=["tube"])
    gm.graph.add_node("c", name="Gamma", lines=["central"], modes=["tube"])
    gm.graph.add_edge("a", "b", line="central", time_distance=5.0, base_time=5.0, fragility=0.0, mode="tube", schedules={})
    gm.graph.add_edge("b", "c", line="central", time_distance=4.0, base_time=4.0, fragility=0.0, mode="tube", schedules={})
    return gm


@pytest.fixture
def two_line_graph():
    gm = GraphManager()
    gm.graph.add_node("a", name="Alpha", lines=["central"], modes=["tube"])
    gm.graph.add_node("b", name="Beta", lines=["central", "victoria"], modes=["tube"])
    gm.graph.add_node("c", name="Gamma", lines=["victoria"], modes=["tube"])
    gm.graph.add_edge("a", "b", line="central", time_distance=3.0, base_time=3.0, fragility=0.0, mode="tube", schedules={})
    gm.graph.add_edge("b", "c", line="victoria", time_distance=3.0, base_time=3.0, fragility=0.0, mode="tube", schedules={})
    return gm


class TestTimeToMinutes:
    def test_float_returned_unchanged(self):
        result = GraphManager.time_to_minutes(570.0)

        assert result == 570.0

    def test_integer_converted_to_float(self):
        result = GraphManager.time_to_minutes(90)

        assert result == 90.0

    def test_datetime_object_uses_hour_and_minute(self):
        dt = datetime(2026, 3, 2, 9, 30)

        result = GraphManager.time_to_minutes(dt)

        assert result == 570.0

    def test_time_object_uses_hour_and_minute(self):
        t = time(9, 30)

        result = GraphManager.time_to_minutes(t)

        assert result == 570.0

    def test_string_hhmm_parsed_correctly(self):
        result = GraphManager.time_to_minutes("09:30")

        assert result == 570.0

    def test_midnight_string_returns_zero(self):
        result = GraphManager.time_to_minutes("00:00")

        assert result == 0.0

    def test_invalid_string_raises_value_error(self):
        with pytest.raises(ValueError):
            GraphManager.time_to_minutes("not-a-time")

    def test_invalid_type_raises_value_error(self):
        with pytest.raises(ValueError):
            GraphManager.time_to_minutes([9, 30])


class TestGetStationCrowdingPenalty:
    def test_station_absent_returns_zero(self):
        gm = GraphManager()
        crowding_data = {}

        penalty = gm._get_station_crowding_penalty("sta_x", "central", crowding_data)

        assert penalty == 0.0

    def test_line_absent_for_station_returns_zero(self):
        gm = GraphManager()
        crowding_data = {"sta_a": {"victoria": [{"capacity_percentage": 60}]}}

        penalty = gm._get_station_crowding_penalty("sta_a", "central", crowding_data)

        assert penalty == 0.0

    def test_zero_capacity_returns_zero_penalty(self):
        gm = GraphManager()
        crowding_data = {"sta_a": {"central": [{"capacity_percentage": 0}]}}

        penalty = gm._get_station_crowding_penalty("sta_a", "central", crowding_data)

        assert penalty == 0.0

    def test_50_percent_capacity_returns_half_penalty(self):
        gm = GraphManager()
        crowding_data = {"sta_a": {"central": [{"capacity_percentage": 50}]}}

        penalty = gm._get_station_crowding_penalty("sta_a", "central", crowding_data)

        assert penalty == pytest.approx(0.5, abs=0.01)

    def test_100_percent_capacity_returns_one(self):
        gm = GraphManager()
        crowding_data = {"sta_a": {"central": [{"capacity_percentage": 100}]}}

        penalty = gm._get_station_crowding_penalty("sta_a", "central", crowding_data)

        assert penalty == pytest.approx(1.0, abs=0.01)

    def test_over_100_percent_capped_above_one(self):
        gm = GraphManager()
        crowding_data = {"sta_a": {"central": [{"capacity_percentage": 200}]}}

        penalty = gm._get_station_crowding_penalty("sta_a", "central", crowding_data)

        assert penalty <= 1.0 + 0.5

    def test_empty_time_slices_returns_zero(self):
        gm = GraphManager()
        crowding_data = {"sta_a": {"central": []}}

        penalty = gm._get_station_crowding_penalty("sta_a", "central", crowding_data)

        assert penalty == 0.0

    def test_multiple_time_slices_averaged(self):
        gm = GraphManager()
        crowding_data = {"sta_a": {"central": [
            {"capacity_percentage": 0},
            {"capacity_percentage": 100}
        ]}}

        penalty = gm._get_station_crowding_penalty("sta_a", "central", crowding_data)

        assert penalty == pytest.approx(0.5, abs=0.01)


class TestCountChangesInPath:
    def test_empty_path_returns_zero(self, simple_graph):
        result = simple_graph.count_changes_in_path([])

        assert result == 0

    def test_single_station_returns_zero(self, simple_graph):
        result = simple_graph.count_changes_in_path(["a"])

        assert result == 0

    def test_same_line_throughout_returns_zero(self, simple_graph):
        result = simple_graph.count_changes_in_path(["a", "b", "c"])

        assert result == 0

    def test_one_line_change_returns_one(self, two_line_graph):
        result = two_line_graph.count_changes_in_path(["a", "b", "c"])

        assert result == 1

    def test_two_line_changes(self):
        gm = GraphManager()
        gm.graph.add_node("a")
        gm.graph.add_node("b")
        gm.graph.add_node("c")
        gm.graph.add_node("d")
        gm.graph.add_edge("a", "b", line="central")
        gm.graph.add_edge("b", "c", line="victoria")
        gm.graph.add_edge("c", "d", line="central")

        result = gm.count_changes_in_path(["a", "b", "c", "d"])

        assert result == 2


class TestApplyDisruptions:
    def test_suspension_removes_all_line_edges(self, db_session, simple_graph):
        db_session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        db_session.add(Line(id="central", name="Central", mode_name="tube"))
        db_session.add(Disruption(
            id="d-suspend", line_id="central", type="lineStatus",
            category="service disruption", description="service suspended",
            summary="", created="2026-01-01", is_active=True,
        ))
        db_session.commit()

        simple_graph.apply_disruptions(db_session)

        assert not simple_graph.graph.has_edge("a", "b")
        assert not simple_graph.graph.has_edge("b", "c")

    def test_closure_removes_all_line_edges(self, db_session, simple_graph):
        db_session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        db_session.add(Line(id="central", name="Central", mode_name="tube"))
        db_session.add(Disruption(
            id="d-closure", line_id="central", type="lineStatus",
            category="closure", description="",
            summary="", created="2026-01-01", is_active=True,
        ))
        db_session.commit()

        simple_graph.apply_disruptions(db_session)

        assert not simple_graph.graph.has_edge("a", "b")

    def test_severe_delay_multiplies_time_by_1_5(self, db_session, simple_graph):
        db_session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        db_session.add(Line(id="central", name="Central", mode_name="tube"))
        db_session.add(Disruption(
            id="d-severe", line_id="central", type="lineStatus",
            category="severe delays", description="severe delay reported",
            summary="", created="2026-01-01", is_active=True,
        ))
        db_session.commit()
        original_time = simple_graph.graph["a"]["b"]["base_time"]

        simple_graph.apply_disruptions(db_session)

        assert simple_graph.graph["a"]["b"]["time_distance"] == pytest.approx(original_time * 1.5)

    def test_minor_delay_multiplies_time_by_1_25(self, db_session, simple_graph):
        db_session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        db_session.add(Line(id="central", name="Central", mode_name="tube"))
        db_session.add(Disruption(
            id="d-delay", line_id="central", type="lineStatus",
            category="minor delays", description="slight delay",
            summary="", created="2026-01-01", is_active=True,
        ))
        db_session.commit()
        original_time = simple_graph.graph["a"]["b"]["base_time"]

        simple_graph.apply_disruptions(db_session)

        assert simple_graph.graph["a"]["b"]["time_distance"] == pytest.approx(original_time * 1.25)

    def test_disruption_on_other_line_leaves_edges_unchanged(self, db_session, simple_graph):
        db_session.add(Mode(name="tube", isTflService=True, isScheduledService=True))
        db_session.add(Line(id="central", name="Central", mode_name="tube"))
        db_session.add(Line(id="victoria", name="Victoria", mode_name="tube"))
        db_session.add(Disruption(
            id="d-other", line_id="victoria", type="lineStatus",
            category="service disruption", description="suspended",
            summary="", created="2026-01-01", is_active=True,
        ))
        db_session.commit()

        simple_graph.apply_disruptions(db_session)

        assert simple_graph.graph.has_edge("a", "b")
        assert simple_graph.graph.has_edge("b", "c")


class TestBuildStateSpaceGraph:
    def test_state_nodes_created_per_station_line_pair(self, simple_graph):
        state_graph = simple_graph.build_state_space_graph()

        nodes = list(state_graph.nodes())
        assert ("a", "central") in nodes
        assert ("b", "central") in nodes
        assert ("c", "central") in nodes

    def test_avoided_line_edges_excluded(self, two_line_graph):
        state_graph = two_line_graph.build_state_space_graph(avoid_lines=["victoria"])

        nodes = list(state_graph.nodes())
        assert not any(line == "victoria" for _, line in nodes)

    def test_transfer_edges_added_for_multi_line_station(self, two_line_graph):
        state_graph = two_line_graph.build_state_space_graph()

        assert state_graph.has_edge(("b", "central"), ("b", "victoria"))

    def test_metropolitan_line_gets_higher_transfer_penalty(self):
        gm = GraphManager()
        gm.graph.add_node("x", name="X", lines=["metropolitan", "circle"], modes=["tube"])
        gm.graph.add_node("y", name="Y", lines=["metropolitan"], modes=["tube"])
        gm.graph.add_node("z", name="Z", lines=["circle"], modes=["tube"])
        gm.graph.add_edge("x", "y", line="metropolitan", time_distance=3.0, base_time=3.0, fragility=0.0, mode="tube", schedules={})
        gm.graph.add_edge("x", "z", line="circle", time_distance=3.0, base_time=3.0, fragility=0.0, mode="tube", schedules={})

        state_graph = gm.build_state_space_graph()

        metro_transfer = state_graph["x", "metropolitan"]["x", "circle"]["weight"]
        non_metro_transfer = state_graph.get_edge_data(("x", "circle"), ("x", "metropolitan"), {}).get("weight", 0)

        assert metro_transfer > 5.0


class TestFindPathWithChangePenalty:
    def test_single_line_path_found(self, simple_graph):
        path = simple_graph.find_path_with_change_penalty("a", "c")

        assert path[0] == "a"
        assert path[-1] == "c"

    def test_consecutive_duplicates_removed(self, two_line_graph):
        path = two_line_graph.find_path_with_change_penalty("a", "c")

        for i in range(len(path) - 1):
            assert path[i] != path[i + 1]

    def test_no_path_raises_networkx_exception(self):
        gm = GraphManager()
        gm.graph.add_node("isolated_a")
        gm.graph.add_node("isolated_b")
        gm.graph.add_edge("isolated_a", "isolated_b", line="central", time_distance=5.0, base_time=5.0, fragility=0.0, mode="tube", schedules={})
        gm.graph.add_node("isolated_c")

        with pytest.raises(nx.NetworkXNoPath):
            gm.find_path_with_change_penalty("isolated_a", "isolated_c")

    def test_max_changes_zero_blocks_multi_line_path(self, two_line_graph):
        with pytest.raises(nx.NetworkXNoPath):
            two_line_graph.find_path_with_change_penalty(
                "a", "c",
                context={"user_preferences": {"max_changes": 0}},
                max_changes=0
            )

    def test_station_not_in_graph_raises_node_not_found(self, simple_graph):
        with pytest.raises(nx.NodeNotFound):
            simple_graph.find_path_with_change_penalty("a", "nonexistent_station")
