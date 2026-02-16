"""
Routing Strategy Interface

Provides pluggable routing algorithms with different optimization objectives:
- Fastest: Minimize travel time
- Robust: Minimize disruption risk
- Low Crowding: Avoid crowded stations/lines
- ML Hybrid: Weighted combination of multiple factors
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
import logging


class RoutingStrategy(ABC):
    """
    Abstract base class for routing strategies.
    
    Each strategy defines how to calculate edge weights for pathfinding,
    allowing different optimization objectives.
    """
    
    def __init__(self, name: str):
        """
        Initialize routing strategy.
        
        Args:
            name: Human-readable name for this strategy
        """
        self.name = name
        self.logger = logging.getLogger(__name__)
    
    @abstractmethod
    def calculate_edge_weight(self, edge_data: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate the weight for an edge in the routing graph.
        
        Args:
            edge_data: Dictionary containing edge attributes:
                - 'base_time': Base travel time in minutes
                - 'time_distance': Current travel time (may be disruption-adjusted)
                - 'fragility': Disruption probability/reliability score
                - 'line': Line ID
                - 'mode': Transport mode
                - 'disrupted': Boolean flag
            context: Dictionary with routing context:
                - 'current_time': datetime object
                - 'crowding_data': Dict of station crowding metrics
                - 'user_preferences': Dict of user weightings
                - 'predictor': DisruptionPredictor instance
                
        Returns:
            Weight value (lower = better/preferred)
        """
        pass
    
    def get_description(self) -> str:
        """Return a description of this routing strategy."""
        return f"{self.name} routing strategy"


class FastestRouteStrategy(RoutingStrategy):
    """
    Optimize for minimum travel time.
    
    Uses time_distance directly, which includes current disruption impacts.
    """
    
    def __init__(self):
        super().__init__("Fastest")
    
    def calculate_edge_weight(self, edge_data: Dict[str, Any], context: Dict[str, Any]) -> float:
        """Return travel time as weight."""
        return edge_data.get('time_distance', edge_data.get('base_time', 5.0))
    
    def get_description(self) -> str:
        return "Minimizes total travel time, accounting for current disruptions"


class RobustRouteStrategy(RoutingStrategy):
    """
    Optimize for route reliability by avoiding disruption-prone segments.
    
    Combines travel time with fragility score to prefer reliable routes
    even if slightly longer.
    """
    
    def __init__(self, reliability_weight: float = 0.3):
        """
        Initialize robust routing strategy.
        
        Args:
            reliability_weight: How much to weight reliability vs speed (0.0 to 1.0)
                Higher = more emphasis on avoiding disruptions
        """
        super().__init__("Robust")
        self.reliability_weight = reliability_weight
    
    def calculate_edge_weight(self, edge_data: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate weight balancing time and reliability.
        
        Formula: time * (1 + reliability_weight * fragility)
        """
        base_time = edge_data.get('time_distance', edge_data.get('base_time', 5.0))
        fragility = edge_data.get('fragility', 0.0)
        
        # Penalize unreliable edges
        weight = base_time * (1.0 + self.reliability_weight * fragility)
        
        return weight
    
    def get_description(self) -> str:
        return (f"Balances speed with reliability (weight: {self.reliability_weight:.1%}), "
                f"avoiding disruption-prone routes")


class LowCrowdingStrategy(RoutingStrategy):
    """
    Optimize to avoid crowded stations and lines.
    
    Uses crowding data to penalize busy routes, preferring less congested
    alternatives even if slightly longer.
    """
    
    def __init__(self, crowding_weight: float = 0.25):
        """
        Initialize low-crowding routing strategy.
        
        Args:
            crowding_weight: How much to weight crowding avoidance (0.0 to 1.0)
        """
        super().__init__("Low Crowding")
        self.crowding_weight = crowding_weight
    
    def calculate_edge_weight(self, edge_data: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate weight penalizing crowded segments.
        
        Formula: time * (1 + crowding_weight * crowding_penalty)
        """
        base_time = edge_data.get('time_distance', edge_data.get('base_time', 5.0))
        
        # Get crowding penalty from edge data (set by graph manager)
        crowding_penalty = edge_data.get('crowding_penalty', 0.0)
        
        # Apply crowding weight
        weight = base_time * (1.0 + self.crowding_weight * crowding_penalty)
        
        return weight
    
    def get_description(self) -> str:
        return (f"Minimizes crowding exposure (weight: {self.crowding_weight:.1%}), "
                f"preferring less busy routes")


class MLHybridStrategy(RoutingStrategy):
    """
    Multi-objective optimization combining time, reliability, and crowding.
    
    Uses configurable weights to balance multiple factors based on user
    preferences or learned patterns.
    """
    
    def __init__(
        self,
        time_weight: float = 0.5,
        reliability_weight: float = 0.3,
        crowding_weight: float = 0.2
    ):
        """
        Initialize ML hybrid routing strategy.
        
        Args:
            time_weight: Weight for travel time (should sum to 1.0 with others)
            reliability_weight: Weight for route reliability
            crowding_weight: Weight for crowding avoidance
        """
        super().__init__("ML Hybrid")
        
        # Normalize weights to sum to 1.0
        total = time_weight + reliability_weight + crowding_weight
        self.time_weight = time_weight / total
        self.reliability_weight = reliability_weight / total
        self.crowding_weight = crowding_weight / total
    
    def calculate_edge_weight(self, edge_data: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate weighted combination of multiple factors.
        
        Normalizes each factor to comparable scale before combining.
        """
        # Base metrics
        time = edge_data.get('time_distance', edge_data.get('base_time', 5.0))
        fragility = edge_data.get('fragility', 0.0)
        crowding_penalty = edge_data.get('crowding_penalty', 0.0)
        
        # Normalize time to 0-1 scale (assume max reasonable segment = 20 min)
        normalized_time = min(time / 20.0, 1.0)
        
        # Fragility and crowding already in 0-1 range
        
        # Calculate weighted score
        score = (
            self.time_weight * normalized_time +
            self.reliability_weight * fragility +
            self.crowding_weight * crowding_penalty
        )
        
        # Scale back to time units for consistent path costs
        weight = score * time
        
        return weight
    
    def get_description(self) -> str:
        return (f"Optimizes multiple factors: time ({self.time_weight:.1%}), "
                f"reliability ({self.reliability_weight:.1%}), "
                f"crowding ({self.crowding_weight:.1%})")


def get_strategy(mode: str, **kwargs) -> RoutingStrategy:
    """
    Factory function to create routing strategy by name.
    
    Args:
        mode: Strategy name ('fastest', 'robust', 'low_crowding', 'ml_hybrid')
        **kwargs: Strategy-specific parameters
        
    Returns:
        RoutingStrategy instance
        
    Raises:
        ValueError: If mode is not recognized
    """
    mode_lower = mode.lower().replace('-', '_').replace(' ', '_')
    
    if mode_lower == 'fastest':
        return FastestRouteStrategy()
    elif mode_lower == 'robust':
        return RobustRouteStrategy(**kwargs)
    elif mode_lower == 'low_crowding':
        return LowCrowdingStrategy(**kwargs)
    elif mode_lower == 'ml_hybrid':
        return MLHybridStrategy(**kwargs)
    else:
        raise ValueError(f"Unknown routing mode: {mode}")


def list_available_strategies() -> list[dict]:
    """
    Get list of all available routing strategies with descriptions.
    
    Returns:
        List of dicts with 'name', 'id', and 'description' keys
    """
    strategies = [
        FastestRouteStrategy(),
        RobustRouteStrategy(),
        LowCrowdingStrategy(),
        MLHybridStrategy()
    ]
    
    return [
        {
            'id': s.name.lower().replace(' ', '_'),
            'name': s.name,
            'description': s.get_description()
        }
        for s in strategies
    ]
