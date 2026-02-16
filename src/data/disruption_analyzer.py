"""
Disruption Analysis Module

Provides Bayesian-inspired reliability scoring based on historical disruption data.
Calculates line and station fragility scores for use in routing optimization.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import logging

from .db_models import Disruption, DisruptedStop


class DisruptionPredictor:
    """
    Analyzes historical disruption patterns to predict route reliability.
    
    Uses a Bayesian approach combining prior beliefs with observed data:
    - Prior: Base reliability assumption for all lines (default: 95%)
    - Observed: Actual disruption frequency from database
    """
    
    def __init__(self, db: Session, lookback_days: int = 90, prior_reliability: float = 0.95):
        """
        Initialize the disruption predictor.
        
        Args:
            db: SQLAlchemy database session
            lookback_days: Number of days of historical data to analyze
            prior_reliability: Prior belief about line reliability (0.0 to 1.0)
        """
        self.db = db
        self.lookback_days = lookback_days
        self.prior_reliability = prior_reliability
        self.logger = logging.getLogger(__name__)
        
        # Cache for computed scores
        self._line_scores: Dict[str, float] = {}
        self._station_scores: Dict[str, float] = {}
        self._time_factors: Dict[str, float] = {}
    
    def calculate_line_reliability_scores(self) -> Dict[str, float]:
        """
        Calculate reliability score for each line based on historical disruptions.
        
        Returns:
            Dictionary mapping line_id -> reliability_score (0.0 to 1.0)
            Higher score = more reliable (fewer/shorter disruptions)
        """
        if self._line_scores:
            return self._line_scores
        
        cutoff_date = (datetime.now() - timedelta(days=self.lookback_days)).isoformat()
        
        # Count disruptions per line in lookback period
        disruption_counts = self.db.query(
            Disruption.line_id,
            func.count(Disruption.id).label("disruption_count"),
            func.avg(Disruption.duration_minutes).label("avg_duration")
        ).filter(
            Disruption.created >= cutoff_date
        ).group_by(
            Disruption.line_id
        ).all()
        
        # Get all unique lines to ensure we score even lines with no disruptions
        all_lines = self.db.query(Disruption.line_id).distinct().all()
        line_ids = {line[0] for line in all_lines}
        
        # Calculate scores using Bayesian update
        for line_id in line_ids:
            # Find disruption data for this line
            line_data = next((d for d in disruption_counts if d.line_id == line_id), None)
            
            if line_data:
                disruption_count = line_data.disruption_count
                avg_duration = float(line_data.avg_duration) if line_data.avg_duration else 60.0  # Default 1 hour if no duration
                
                # Calculate disruption impact factor
                # More disruptions and longer durations = lower reliability
                # Normalize: assume 1 disruption per 10 days is acceptable
                expected_disruptions = self.lookback_days / 10.0
                disruption_ratio = float(disruption_count) / expected_disruptions
                
                # Duration penalty: longer disruptions hurt more
                duration_factor = min(avg_duration / 120.0, 2.0)  # Cap at 2x penalty for very long
                
                # Combine factors
                impact = disruption_ratio * duration_factor
                
                # Bayesian update: weight prior with observed
                # More observations = more weight on observed data
                weight = min(float(disruption_count) / 10.0, 0.8)  # Cap at 80% observed weight
                observed_reliability = max(0.0, 1.0 - (impact * 0.1))  # Impact scaled to 0-1
                
                reliability = (1 - weight) * self.prior_reliability + weight * observed_reliability
            else:
                # No disruptions = use prior
                reliability = self.prior_reliability
            
            # Convert to fragility (inverse of reliability) for routing
            fragility = 1.0 - reliability
            self._line_scores[line_id] = fragility
        
        self.logger.info(f"Calculated reliability scores for {len(self._line_scores)} lines")
        return self._line_scores
    
    def calculate_station_reliability_scores(self) -> Dict[str, float]:
        """
        Calculate reliability score for each station based on disruption involvement.
        
        Returns:
            Dictionary mapping station_id -> fragility_score (0.0 to 1.0)
            Higher score = more frequently disrupted
        """
        if self._station_scores:
            return self._station_scores
        
        cutoff_date = (datetime.now() - timedelta(days=self.lookback_days)).isoformat()
        
        # Count how many disruptions affected each station
        station_counts = self.db.query(
            DisruptedStop.station_id,
            func.count(DisruptedStop.disruption_id).label("disruption_count")
        ).join(
            Disruption, DisruptedStop.disruption_id == Disruption.id
        ).filter(
            Disruption.created >= cutoff_date
        ).group_by(
            DisruptedStop.station_id
        ).all()
        
        # Calculate fragility scores
        max_count = max([s.disruption_count for s in station_counts], default=1)
        
        for station_data in station_counts:
            # Normalize to 0-1 range, with some baseline fragility
            normalized = float(station_data.disruption_count) / float(max_count)
            fragility = 0.1 + (normalized * 0.4)  # Range: 0.1 to 0.5
            self._station_scores[station_data.station_id] = fragility
        
        self.logger.info(f"Calculated reliability scores for {len(self._station_scores)} stations")
        return self._station_scores
    
    def get_time_context_factors(self, current_time: Optional[datetime] = None) -> Dict[str, float]:
        """
        Calculate time-of-day adjustment factors based on historical patterns.
        
        Args:
            current_time: Time to get context for (defaults to now)
            
        Returns:
            Dictionary with time context multipliers:
            {
                'hour_of_day': int (0-23),
                'is_peak': bool,
                'is_weekend': bool,
                'disruption_multiplier': float (1.0 = average)
            }
        """
        if current_time is None:
            current_time = datetime.now()
        
        hour = current_time.hour
        day_of_week = current_time.weekday()  # 0=Monday, 6=Sunday
        
        # Define peak hours (weekdays 7-10am and 5-8pm)
        is_weekend = day_of_week >= 5
        is_morning_peak = not is_weekend and 7 <= hour <= 10
        is_evening_peak = not is_weekend and 17 <= hour <= 20
        is_peak = is_morning_peak or is_evening_peak
        
        # Disruption multiplier: peak times are more likely to have issues
        if is_peak:
            multiplier = 1.3
        elif is_weekend:
            multiplier = 0.7  # Weekends typically have fewer issues
        elif 23 <= hour or hour <= 5:
            multiplier = 0.5  # Night services very reliable (or non-existent)
        else:
            multiplier = 1.0
        
        return {
            'hour_of_day': hour,
            'is_peak': is_peak,
            'is_weekend': is_weekend,
            'disruption_multiplier': multiplier
        }
    
    def predict_edge_fragility(
        self,
        line_id: str,
        from_station_id: str,
        to_station_id: str,
        current_time: Optional[datetime] = None
    ) -> float:
        """
        Predict fragility for a specific edge in the network graph.
        
        Combines line reliability, station reliability, and time context.
        
        Args:
            line_id: Line identifier
            from_station_id: Origin station
            to_station_id: Destination station
            current_time: Time context for prediction
            
        Returns:
            Fragility score (0.0 to 1.0), where higher = less reliable
        """
        # Get component scores
        line_scores = self.calculate_line_reliability_scores()
        station_scores = self.calculate_station_reliability_scores()
        time_context = self.get_time_context_factors(current_time)
        
        # Line fragility (primary factor)
        line_fragility = line_scores.get(line_id, 0.05)  # Default to low fragility
        
        # Station fragility (average of endpoints)
        from_fragility = station_scores.get(from_station_id, 0.05)
        to_fragility = station_scores.get(to_station_id, 0.05)
        station_fragility = (from_fragility + to_fragility) / 2.0
        
        # Combine: line is 70% weight, stations 30%
        base_fragility = 0.7 * line_fragility + 0.3 * station_fragility
        
        # Apply time context multiplier
        adjusted_fragility = base_fragility * time_context['disruption_multiplier']
        
        # Clamp to valid range
        return max(0.0, min(1.0, adjusted_fragility))
    
    def clear_cache(self):
        """Clear cached scores to force recalculation."""
        self._line_scores = {}
        self._station_scores = {}
        self._time_factors = {}
