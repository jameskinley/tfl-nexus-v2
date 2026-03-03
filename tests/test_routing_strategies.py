import pytest

from graph.routing_strategies import (
    FastestRouteStrategy,
    RobustRouteStrategy,
    LowCrowdingStrategy,
    MLHybridStrategy,
    get_strategy,
)


class TestFastestRouteStrategy:
    def test_returns_time_distance_from_edge(self):
        strategy = FastestRouteStrategy()
        edge_data = {"time_distance": 8.0, "base_time": 10.0, "fragility": 0.5}

        weight = strategy.calculate_edge_weight(edge_data, {})

        assert weight == 8.0

    def test_falls_back_to_base_time_when_no_time_distance(self):
        strategy = FastestRouteStrategy()
        edge_data = {"base_time": 10.0, "fragility": 0.5}

        weight = strategy.calculate_edge_weight(edge_data, {})

        assert weight == 10.0

    def test_uses_default_when_no_time_fields(self):
        strategy = FastestRouteStrategy()

        weight = strategy.calculate_edge_weight({}, {})

        assert weight == 5.0


class TestRobustRouteStrategy:
    def test_zero_fragility_returns_base_time(self):
        strategy = RobustRouteStrategy(reliability_weight=0.3)
        edge_data = {"time_distance": 10.0, "fragility": 0.0}

        weight = strategy.calculate_edge_weight(edge_data, {})

        assert weight == pytest.approx(10.0)

    def test_full_fragility_applies_maximum_penalty(self):
        strategy = RobustRouteStrategy(reliability_weight=0.3)
        edge_data = {"time_distance": 10.0, "fragility": 1.0}

        weight = strategy.calculate_edge_weight(edge_data, {})

        assert weight == pytest.approx(10.0 * (1.0 + 0.3 * 1.0))

    def test_penalty_is_multiplicative_with_fragility(self):
        strategy = RobustRouteStrategy(reliability_weight=0.5)
        edge_data = {"time_distance": 4.0, "fragility": 0.5}

        weight = strategy.calculate_edge_weight(edge_data, {})

        assert weight == pytest.approx(4.0 * (1.0 + 0.5 * 0.5))


class TestLowCrowdingStrategy:
    def test_zero_crowding_returns_base_time(self):
        strategy = LowCrowdingStrategy(crowding_weight=0.25)
        edge_data = {"time_distance": 6.0, "crowding_penalty": 0.0}

        weight = strategy.calculate_edge_weight(edge_data, {})

        assert weight == pytest.approx(6.0)

    def test_full_crowding_applies_maximum_penalty(self):
        strategy = LowCrowdingStrategy(crowding_weight=0.25)
        edge_data = {"time_distance": 6.0, "crowding_penalty": 1.0}

        weight = strategy.calculate_edge_weight(edge_data, {})

        assert weight == pytest.approx(6.0 * 1.25)

    def test_crowding_penalty_is_multiplicative(self):
        strategy = LowCrowdingStrategy(crowding_weight=0.5)
        edge_data = {"time_distance": 8.0, "crowding_penalty": 0.4}

        weight = strategy.calculate_edge_weight(edge_data, {})

        assert weight == pytest.approx(8.0 * (1.0 + 0.5 * 0.4))


class TestMLHybridStrategy:
    def test_weights_normalized_to_sum_to_one(self):
        strategy = MLHybridStrategy(time_weight=2.0, reliability_weight=1.0, crowding_weight=1.0)

        total = strategy.time_weight + strategy.reliability_weight + strategy.crowding_weight

        assert total == pytest.approx(1.0)

    def test_equal_weights_each_becomes_one_third(self):
        strategy = MLHybridStrategy(time_weight=1.0, reliability_weight=1.0, crowding_weight=1.0)

        assert strategy.time_weight == pytest.approx(1 / 3)
        assert strategy.reliability_weight == pytest.approx(1 / 3)
        assert strategy.crowding_weight == pytest.approx(1 / 3)

    def test_already_summing_weights_unchanged(self):
        strategy = MLHybridStrategy(time_weight=0.5, reliability_weight=0.3, crowding_weight=0.2)

        assert strategy.time_weight == pytest.approx(0.5)
        assert strategy.reliability_weight == pytest.approx(0.3)
        assert strategy.crowding_weight == pytest.approx(0.2)

    def test_zero_time_returns_zero_weight(self):
        strategy = MLHybridStrategy()
        edge_data = {"time_distance": 0.0, "fragility": 0.0, "crowding_penalty": 0.0}

        weight = strategy.calculate_edge_weight(edge_data, {})

        assert weight == pytest.approx(0.0)

    def test_time_capped_at_20_min_for_normalisation(self):
        strategy = MLHybridStrategy(time_weight=1.0, reliability_weight=0.0, crowding_weight=0.0)
        edge_short = {"time_distance": 20.0, "fragility": 0.0, "crowding_penalty": 0.0}
        edge_long = {"time_distance": 100.0, "fragility": 0.0, "crowding_penalty": 0.0}

        weight_short = strategy.calculate_edge_weight(edge_short, {})
        weight_long = strategy.calculate_edge_weight(edge_long, {})

        assert weight_short != weight_long


class TestGetStrategy:
    def test_fastest_strategy_created(self):
        strategy = get_strategy("fastest")

        assert isinstance(strategy, FastestRouteStrategy)

    def test_robust_strategy_created(self):
        strategy = get_strategy("robust")

        assert isinstance(strategy, RobustRouteStrategy)

    def test_low_crowding_strategy_created(self):
        strategy = get_strategy("low_crowding")

        assert isinstance(strategy, LowCrowdingStrategy)

    def test_ml_hybrid_strategy_created(self):
        strategy = get_strategy("ml_hybrid")

        assert isinstance(strategy, MLHybridStrategy)

    def test_hyphenated_name_normalised(self):
        strategy = get_strategy("low-crowding")

        assert isinstance(strategy, LowCrowdingStrategy)

    def test_space_in_name_normalised(self):
        strategy = get_strategy("ml hybrid")

        assert isinstance(strategy, MLHybridStrategy)

    def test_uppercase_name_normalised(self):
        strategy = get_strategy("FASTEST")

        assert isinstance(strategy, FastestRouteStrategy)

    def test_unknown_mode_raises_value_error(self):
        with pytest.raises(ValueError):
            get_strategy("unknown_mode")
