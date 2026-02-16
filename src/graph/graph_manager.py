import networkx as nx
from sqlalchemy.orm import Session
from data import db_models
from logging import getLogger
from datetime import datetime, time
from typing import Dict, Any, Optional
from .routing_strategies import RoutingStrategy

logger = getLogger(__name__)

class GraphManager:
    """
    Graph manager for building network graphs from station data.
    
    Builds a NetworkX graph from SQLAlchemy database models using:
    - Stations as nodes
    - Route connections (StationIntervals) as edges
    - Timetable data for edge weights (time_distance)
    """
    def __init__(self):
        self.graph = nx.Graph()  # treat as undirected for simplicity

    @staticmethod
    def time_to_minutes(time_input) -> float:
        """
        Convert time to minutes from midnight.
        
        Args:
            time_input: Can be:
                - float: Already in minutes from midnight
                - datetime.time: Time object
                - datetime.datetime: Datetime object (uses time part)
                - str: Time string in format "HH:MM" (24-hour)
                
        Returns:
            Minutes from midnight as float
            
        Examples:
            >>> GraphManager.time_to_minutes(9.5 * 60)  # 9:30 AM
            570.0
            >>> GraphManager.time_to_minutes(time(9, 30))
            570.0
            >>> GraphManager.time_to_minutes("09:30")
            570.0
        """
        if isinstance(time_input, (int, float)):
            return float(time_input)
        elif isinstance(time_input, datetime):
            return time_input.hour * 60 + time_input.minute
        elif isinstance(time_input, time):
            return time_input.hour * 60 + time_input.minute
        elif isinstance(time_input, str):
            # Parse "HH:MM" format
            parts = time_input.split(':')
            if len(parts) == 2:
                hours, minutes = int(parts[0]), int(parts[1])
                return hours * 60 + minutes
        
        raise ValueError(f"Cannot convert {type(time_input)} to minutes from midnight")


    def build_graph_from_db(self, session: Session):
        """
        Build graph from database using Route -> StationInterval relationships.
        
        Args:
            session: Active SQLAlchemy session
        """
        logger.info("Building graph from database...")

        routes = session.query(db_models.Route).all()
        
        node_count = 0
        edge_count = 0
        
        for route in routes:
            intervals = sorted(route.station_intervals, key=lambda x: x.ordinal)
            
            for interval in intervals:
                station = interval.station
                if not station:
                    logger.warning(f"Station not loaded for interval at ordinal {interval.ordinal}")
                    continue
                    
                if station.id not in self.graph:
                    self.graph.add_node(
                        station.id,
                        name=station.name,
                        naptans=[n.naptan_code for n in station.naptans],
                        modes=[mode.name for mode in station.modes],
                        lines=[line.id for line in station.lines],
                        lat=station.lat,
                        lon=station.lon
                    )
                    node_count += 1
            
            if len(intervals) < 2:
                continue

            schedule_times = {}
            for schedule in route.schedules:
                schedule_times[schedule.name] = {
                    'first_journey': schedule.first_journey_time,
                    'last_journey': schedule.last_journey_time,
                    'periods': []
                }
                for period in schedule.periods:
                    schedule_times[schedule.name]['periods'].append({
                        'from_time': period.from_time,
                        'to_time': period.to_time,
                        'frequency_min': period.frequency_min,
                        'frequency_max': period.frequency_max
                    })
            
            for i in range(len(intervals) - 1):
                current_interval = intervals[i]
                next_interval = intervals[i + 1]

                if not current_interval.station or not next_interval.station:
                    logger.warning(f"Skipping edge creation: station not loaded")
                    continue
                
                station_a = current_interval.station.id
                station_b = next_interval.station.id
                
                time_distance = 0.0
                if next_interval.time_to_arrival and current_interval.time_to_arrival:
                    time_distance = next_interval.time_to_arrival - current_interval.time_to_arrival
                elif next_interval.time_to_arrival:
                    time_distance = next_interval.time_to_arrival

                if self.graph.has_edge(station_a, station_b):
                    existing_time = self.graph[station_a][station_b].get('base_time', float('inf'))
                    if time_distance < existing_time and time_distance > 0:
                        self.graph[station_a][station_b]['base_time'] = time_distance
                        self.graph[station_a][station_b]['time_distance'] = time_distance
                        self.graph[station_a][station_b]['line'] = route.line_id
                        self.graph[station_a][station_b]['mode'] = route.line.mode_name
                        self.graph[station_a][station_b]['schedules'] = schedule_times
                else:
                    self.graph.add_edge(
                        station_a,
                        station_b,
                        base_time=time_distance if time_distance > 0 else 1.0,
                        time_distance=time_distance if time_distance > 0 else 1.0,
                        fragility=0.0,
                        line=route.line_id,
                        mode=route.line.mode_name,
                        schedules=schedule_times
                    )
                    edge_count += 1
        
        logger.info(f"Graph built: {node_count} nodes, {edge_count} edges")
        return self.graph

    def get_dynamic_weight(self, station_a: str, station_b: str, current_time: float) -> float:
        """
        Get dynamic edge weight based on current time and active schedules.
        
        Args:
            station_a: Source station ID
            station_b: Target station ID  
            current_time: Current time in minutes from midnight (e.g., 9:30 AM = 570)
            
        Returns:
            Travel time in minutes, adjusted for current schedule/frequency
        """
        if not self.graph.has_edge(station_a, station_b):
            return float('inf')
        
        edge_data = self.graph[station_a][station_b]
        base_time = edge_data.get('base_time', 1.0)
        schedules = edge_data.get('schedules', {})
        
        wait_time = 0.0
        for _, schedule_data in schedules.items():
            first = schedule_data.get('first_journey', 0)
            last = schedule_data.get('last_journey', 24 * 60)
            
            if first <= current_time <= last:
                for period in schedule_data.get('periods', []):
                    if period['from_time'] <= current_time <= period['to_time']:
                        freq_min = period.get('frequency_min', 0)
                        freq_max = period.get('frequency_max', 0)
                        if freq_min and freq_max:
                            avg_frequency = (freq_min + freq_max) / 2
                            wait_time = avg_frequency / 2
                        break
                break
        
        return base_time + wait_time

    def add_edge(self, stop_a: str, stop_b: str, time_distance: float = 0.0, 
                 fragility: float = 0.0, line: str = "", mode: str = ""):
        """
        Manually add an edge between two stations.
        
        Args:
            stop_a: Station ID for first station
            stop_b: Station ID for second station
            time_distance: Travel time in minutes (default: 0.0)
            fragility: Fragility score for reliability (default: 0.0)
            line: Line ID (default: "")
            mode: Mode name (default: "")
        """
        self.graph.add_edge(
            stop_a, 
            stop_b, 
            fragility=fragility, 
            time_distance=time_distance, 
            line=line, 
            mode=mode
        )

    def route_time_only(self, start_stop, end_stop, current_time=None):
        """
        Find shortest path by time.
        
        Args:
            start_stop: Source station ID
            end_stop: Destination station ID
            current_time: Optional current time. Can be:
                         - Minutes from midnight (float)
                         - datetime.time or datetime.datetime object
                         - String in "HH:MM" format
                         If provided, uses dynamic weights based on schedules.
        
        Returns:
            List of station IDs representing the path
        """
        if current_time is not None:
            time_minutes = self.time_to_minutes(current_time)
            weight_func = lambda u, v, d: self.get_dynamic_weight(u, v, time_minutes)
            return nx.shortest_path(self.graph, source=start_stop, target=end_stop, weight=weight_func)
        else:
            # Use static base time weights
            return nx.shortest_path(self.graph, source=start_stop, target=end_stop, weight='time_distance')
    
    def route_fragility_only(self, start_stop, end_stop):
        """
        Find most reliable path (lowest fragility).
        
        Args:
            start_stop: Source station ID
            end_stop: Destination station ID
            
        Returns:
            List of station IDs representing the path
        """
        return nx.shortest_path(self.graph, source=start_stop, target=end_stop, weight='fragility')
    
    def route_combined(self, start_stop, end_stop, time_weight=0.5, current_time=None):
        """
        Find route optimizing both time and fragility.
        
        Args:
            start_stop: Source station ID
            end_stop: Destination station ID
            time_weight: Weight for time (0-1). Fragility weight = 1 - time_weight
            current_time: Optional current time (same formats as route_time_only)
            
        Returns:
            List of station IDs representing the path
        """
        fragility_weight = 1.0 - time_weight
        time_minutes = self.time_to_minutes(current_time) if current_time is not None else None
        
        def combined_weight(u, v, d):
            if time_minutes is not None:
                time_cost = self.get_dynamic_weight(u, v, time_minutes)
            else:
                time_cost = d.get('time_distance', 1.0)
            
            fragility_cost = d.get('fragility', 0.0)
            return (time_weight * time_cost) + (fragility_weight * fragility_cost)
        
        return nx.shortest_path(self.graph, source=start_stop, target=end_stop, weight=combined_weight)

    def apply_disruptions(self, session: Session):
        """
        Apply active disruptions to the graph by modifying edge weights and availability.
        
        Disruption handling:
        - Suspended service: Remove all edges for that line
        - Part suspension: Remove edges between affected stops
        - Severe delays: Increase edge weights by 50%
        - Minor delays: Increase edge weights by 25%
        
        Args:
            session: Database session to query disruptions
        """
        active_disruptions = session.query(db_models.Disruption).filter(
            db_models.Disruption.is_active == True
        ).all()
        
        disrupted_edges = []
        
        for disruption in active_disruptions:
            line_id = disruption.line_id
            category = disruption.category.lower()
            description = (disruption.description or "").lower()
            summary = (disruption.summary or "").lower()
            full_text = f"{category} {description} {summary}"
            
            if "suspend" in full_text or "closure" in full_text:
                edges_to_remove = [
                    (u, v) for u, v, data in self.graph.edges(data=True)
                    if data.get('line') == line_id
                ]
            
                if disruption.affected_stops:
                    affected_station_ids = {stop.station_id for stop in disruption.affected_stops}
                    edges_to_remove = [
                        (u, v) for u, v in edges_to_remove
                        if u in affected_station_ids or v in affected_station_ids
                    ]
                
                for u, v in edges_to_remove:
                    if self.graph.has_edge(u, v):
                        self.graph.remove_edge(u, v)
                        disrupted_edges.append((u, v, line_id, "suspended"))
                        
            elif "delay" in full_text:
                delay_factor = 1.5 if "severe" in full_text else 1.25
                
                edges_to_modify = [
                    (u, v) for u, v, data in self.graph.edges(data=True)
                    if data.get('line') == line_id
                ]

                if disruption.affected_stops:
                    affected_station_ids = {stop.station_id for stop in disruption.affected_stops}
                    edges_to_modify = [
                        (u, v) for u, v in edges_to_modify
                        if u in affected_station_ids or v in affected_station_ids
                    ]
                
                for u, v in edges_to_modify:
                    if self.graph.has_edge(u, v):
                        edge_data = self.graph[u][v]
                        original_time = edge_data.get('base_time', edge_data.get('time_distance', 1.0))
                        edge_data['time_distance'] = original_time * delay_factor
                        edge_data['disrupted'] = True
                        disrupted_edges.append((u, v, line_id, f"delayed_{delay_factor}x"))
        
        logger.info(f"Applied {len(active_disruptions)} disruptions, affecting {len(disrupted_edges)} edges")
        return disrupted_edges

    def apply_fragility_scores(self, session: Session, predictor=None):
        """
        Apply disruption fragility scores to all edges in the graph.
        
        Uses historical disruption data to calculate reliability scores
        for each route segment.
        
        Args:
            session: Database session for querying disruption history
            predictor: Optional DisruptionPredictor instance (creates one if None)
        """
        from data.disruption_analyzer import DisruptionPredictor
        
        if predictor is None:
            predictor = DisruptionPredictor(session)
        
        # Calculate scores
        predictor.calculate_line_reliability_scores()
        predictor.calculate_station_reliability_scores()
        
        # Apply to all edges
        edges_updated = 0
        for u, v, data in self.graph.edges(data=True):
            line_id = data.get('line', '')
            
            # Calculate fragility for this edge
            fragility = predictor.predict_edge_fragility(
                line_id=line_id,
                from_station_id=u,
                to_station_id=v,
                current_time=None  # Use current time
            )
            
            data['fragility'] = fragility
            edges_updated += 1
        
        logger.info(f"Applied fragility scores to {edges_updated} edges")
        return edges_updated

    def apply_crowding_penalties(self, crowding_data: Dict[str, Dict[str, list]]):
        """
        Apply crowding penalties to edges based on station crowding data.
        
        Args:
            crowding_data: Dictionary mapping station_id -> line_id -> crowding metrics list
                Format: {
                    station_id: {
                        line_id: [{
                            'crowding_level': str,
                            'capacity_percentage': float,
                            'time_slice': str
                        }]
                    }
                }
        """
        edges_updated = 0
        
        for u, v, data in self.graph.edges(data=True):
            line_id = data.get('line', '')
            
            # Check crowding for both stations on this line
            u_crowding = self._get_station_crowding_penalty(u, line_id, crowding_data)
            v_crowding = self._get_station_crowding_penalty(v, line_id, crowding_data)
            
            # Average penalty for the edge
            crowding_penalty = (u_crowding + v_crowding) / 2.0
            
            data['crowding_penalty'] = crowding_penalty
            edges_updated += 1
        
        logger.info(f"Applied crowding penalties to {edges_updated} edges")
        return edges_updated

    def _get_station_crowding_penalty(
        self,
        station_id: str,
        line_id: str,
        crowding_data: Dict[str, Dict[str, list]]
    ) -> float:
        """
        Calculate crowding penalty for a station-line combination.
        
        Returns:
            Penalty value 0.0-1.0 (higher = more crowded)
        """
        # Check if we have crowding data for this station
        if station_id not in crowding_data:
            return 0.0
        
        station_data = crowding_data[station_id]
        
        # Check if we have data for this line at this station
        if line_id not in station_data:
            return 0.0
        
        line_crowding = station_data[line_id]
        
        # Average crowding across all time slices
        if not line_crowding:
            return 0.0
        
        total_capacity = sum(c.get('capacity_percentage', 0) for c in line_crowding)
        avg_capacity = total_capacity / len(line_crowding)
        
        # Convert capacity percentage to penalty (0-1 scale)
        # 0-50% capacity = low penalty
        # 50-100% = moderate penalty
        # >100% = high penalty
        if avg_capacity <= 50:
            penalty = avg_capacity / 100.0  # 0.0 to 0.5
        elif avg_capacity <= 100:
            penalty = 0.5 + (avg_capacity - 50) / 100.0  # 0.5 to 1.0
        else:
            penalty = min(1.0, 1.0 + (avg_capacity - 100) / 200.0)  # 1.0+ capped
        
        return penalty

    def route_with_strategy(
        self,
        start_stop: str,
        end_stop: str,
        strategy: RoutingStrategy,
        context: Dict[str, Any]
    ) -> list:
        """
        Find route using a pluggable routing strategy.
        
        Args:
            start_stop: Source station ID
            end_stop: Destination station ID
            strategy: RoutingStrategy instance defining optimization objective
            context: Context dictionary with:
                - 'current_time': datetime object
                - 'crowding_data': Station crowding metrics
                - 'user_preferences': User weightings
                - 'predictor': DisruptionPredictor instance
                
        Returns:
            List of station IDs representing the path
        """
        # Apply strategy weights to all edges
        for u, v, data in self.graph.edges(data=True):
            weight = strategy.calculate_edge_weight(data, context)
            data['strategy_weight'] = weight
        
        # Find shortest path using strategy weights
        try:
            path = nx.shortest_path(
                self.graph,
                source=start_stop,
                target=end_stop,
                weight='strategy_weight'
            )
            logger.info(f"Route found using {strategy.name} strategy: {len(path)} stops")
            return path
        except nx.NetworkXNoPath:
            logger.error(f"No path found between {start_stop} and {end_stop}")
            raise
        except nx.NodeNotFound as e:
            logger.error(f"Station not found in graph: {e}")
            raise

    def build_graph_from_db_with_disruptions(self, session: Session):
        """
        Build graph from database and apply current disruptions.
        
        Args:
            session: Active SQLAlchemy session
            
        Returns:
            NetworkX graph with disruptions applied
        """
        self.build_graph_from_db(session)
        self.apply_disruptions(session)
        return self.graph