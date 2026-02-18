import networkx as nx
from sqlalchemy.orm import Session
from data import db_models
from logging import getLogger
from datetime import datetime, time
from typing import Dict, Any, Optional
from .routing_strategies import RoutingStrategy

logger = getLogger(__name__)

# Constants for change penalties
TRANSFER_TIME_MINUTES = 3.0  # Average time to change lines
CHANGE_PENALTY_BASE = 5.0  # Base penalty for any line change (in time units)
CHANGE_PENALTY_ML_MULTIPLIER = 1.5  # Extra penalty for Metropolitan Line changes

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

    def route_time_only(self, start_stop, end_stop, current_time=None, max_changes=None):
        """
        Find shortest path by time with natural change minimization.
        
        Args:
            start_stop: Source station ID
            end_stop: Destination station ID
            current_time: Optional current time. Can be:
                         - Minutes from midnight (float)
                         - datetime.time or datetime.datetime object
                         - String in "HH:MM" format
                         If provided, uses dynamic weights based on schedules.
            max_changes: Optional maximum number of line changes
        
        Returns:
            List of station IDs representing the path
        """
        # Use state-space graph approach for natural change penalization
        return self.find_path_with_change_penalty(
            start_stop,
            end_stop,
            strategy=None,
            context={'current_time': current_time} if current_time else None,
            max_changes=max_changes
        )
    
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

    def count_changes_in_path(self, path: list[str]) -> int:
        """
        Count the number of line changes in a station path.
        Utility method for reporting purposes.
        
        Args:
            path: List of station IDs
            
        Returns:
            Number of line changes
        """
        if len(path) < 2:
            return 0
        
        changes = 0
        current_line = None
        
        for i in range(len(path) - 1):
            if not self.graph.has_edge(path[i], path[i + 1]):
                continue
            edge_data = self.graph[path[i]][path[i + 1]]
            line = edge_data.get('line')
            
            if line and current_line and line != current_line:
                changes += 1
            
            if line:
                current_line = line
        
        return changes

    def build_state_space_graph(
        self,
        strategy: Optional[RoutingStrategy] = None,
        context: Optional[Dict[str, Any]] = None,
        use_time_weight: bool = True,
        avoid_lines: Optional[list[str]] = None
    ) -> nx.DiGraph:
        """
        Build a state-space graph where nodes are (station_id, line_id) pairs.
        This naturally penalizes line changes during pathfinding.
        
        Args:
            strategy: Optional routing strategy for edge weights
            context: Optional context for strategy
            use_time_weight: Whether to use time-based weights (vs strategy weights)
            avoid_lines: Optional list of line IDs to exclude from routing
            
        Returns:
            Directed graph with (station, line) nodes
        """
        state_graph = nx.DiGraph()
        avoid_lines_set = set(avoid_lines or [])
        
        # Create nodes for each (station, line) combination
        # Map each edge to its line, creating state nodes
        station_lines = {}  # station_id -> set of line_ids
        
        for u, v, data in self.graph.edges(data=True):
            line = data.get('line')
            if not line:
                continue
            
            # Skip lines that should be avoided
            if line in avoid_lines_set:
                continue
                
            # Track which lines serve each station
            if u not in station_lines:
                station_lines[u] = set()
            if v not in station_lines:
                station_lines[v] = set()
            station_lines[u].add(line)
            station_lines[v].add(line)
        
        # Add nodes for each (station, line) pair
        for station_id, lines in station_lines.items():
            for line_id in lines:
                state_node = (station_id, line_id)
                state_graph.add_node(
                    state_node,
                    station_id=station_id,
                    line_id=line_id,
                    **self.graph.nodes[station_id]
                )
        
        # Add movement edges (along the same line)
        for u, v, data in self.graph.edges(data=True):
            line = data.get('line')
            if not line:
                continue
            
            # Skip lines that should be avoided
            if line in avoid_lines_set:
                continue
            
            # Calculate edge weight
            if strategy and context and not use_time_weight:
                weight = strategy.calculate_edge_weight(data, context)
            else:
                weight = data.get('time_distance', data.get('base_time', 5.0))
            
            # Add bidirectional edges for movement along the same line
            state_u = (u, line)
            state_v = (v, line)
            
            state_graph.add_edge(state_u, state_v, weight=weight, **data)
            state_graph.add_edge(state_v, state_u, weight=weight, **data)
        
        # Add transfer edges (line changes at same station)
        for station_id, lines in station_lines.items():
            lines_list = list(lines)
            for i, line1 in enumerate(lines_list):
                for line2 in lines_list[i+1:]:
                    # Calculate transfer penalty
                    transfer_weight = TRANSFER_TIME_MINUTES + CHANGE_PENALTY_BASE
                    
                    # Extra penalty if Metropolitan Line is involved
                    if 'metropolitan' in line1.lower() or 'metropolitan' in line2.lower():
                        transfer_weight *= CHANGE_PENALTY_ML_MULTIPLIER
                    
                    # Add bidirectional transfer edges
                    state_graph.add_edge(
                        (station_id, line1),
                        (station_id, line2),
                        weight=transfer_weight,
                        is_transfer=True,
                        station_id=station_id
                    )
                    state_graph.add_edge(
                        (station_id, line2),
                        (station_id, line1),
                        weight=transfer_weight,
                        is_transfer=True,
                        station_id=station_id
                    )
        
        avoided_msg = f" (avoiding {len(avoid_lines_set)} lines: {', '.join(avoid_lines_set)})" if avoid_lines_set else ""
        logger.info(
            f"Built state-space graph: {state_graph.number_of_nodes()} nodes "
            f"({self.graph.number_of_nodes()} stations), "
            f"{state_graph.number_of_edges()} edges{avoided_msg}"
        )
        
        return state_graph
    
    def find_path_with_change_penalty(
        self,
        start_station: str,
        end_station: str,
        strategy: Optional[RoutingStrategy] = None,
        context: Optional[Dict[str, Any]] = None,
        max_changes: Optional[int] = None
    ) -> list:
        """
        Find optimal path using state-space graph that naturally minimizes changes.
        
        Args:
            start_station: Origin station ID
            end_station: Destination station ID
            strategy: Optional routing strategy
            context: Optional context for strategy
            max_changes: Optional hard limit on changes
            
        Returns:
            List of station IDs (not state nodes)
        """
        # Extract avoid_lines from context
        avoid_lines = None
        if context:
            avoid_lines = context.get('user_preferences', {}).get('avoid_lines', [])
        
        # Build state-space graph
        use_time = strategy is None
        state_graph = self.build_state_space_graph(
            strategy, context, use_time, avoid_lines=avoid_lines
        )
        
        # Find all possible start and end state nodes
        start_states = [n for n in state_graph.nodes() if n[0] == start_station]
        end_states = [n for n in state_graph.nodes() if n[0] == end_station]
        
        if not start_states or not end_states:
            raise nx.NodeNotFound(f"Station not found in state graph")
        
        # Find shortest path considering all start/end combinations
        best_path = None
        best_weight = float('inf')
        
        for start_state in start_states:
            for end_state in end_states:
                try:
                    path = nx.shortest_path(
                        state_graph,
                        start_state,
                        end_state,
                        weight='weight'
                    )
                    
                    # Calculate total weight
                    path_weight = sum(
                        state_graph[path[i]][path[i+1]]['weight']
                        for i in range(len(path) - 1)
                    )
                    
                    # Check max_changes constraint if specified
                    if max_changes is not None:
                        num_changes = sum(
                            1 for i in range(len(path) - 1)
                            if state_graph[path[i]][path[i+1]].get('is_transfer', False)
                        )
                        if num_changes > max_changes:
                            continue
                    
                    if path_weight < best_weight:
                        best_weight = path_weight
                        best_path = path
                        
                except nx.NetworkXNoPath:
                    continue
        
        if not best_path:
            error_msg = f"No path found between {start_station} and {end_station}"
            if avoid_lines:
                error_msg += f" (avoiding lines: {', '.join(avoid_lines)})"
            if max_changes is not None:
                error_msg += f" (max changes: {max_changes})"
            raise nx.NetworkXNoPath(error_msg)
        
        # Convert state path to station path
        station_path = [state[0] for state in best_path]
        
        # Remove consecutive duplicates (from transfers)
        result_path = [station_path[0]]
        for station in station_path[1:]:
            if station != result_path[-1]:
                result_path.append(station)
        
        # Count and log changes
        changes = sum(
            1 for i in range(len(best_path) - 1)
            if best_path[i][1] != best_path[i+1][1] and best_path[i][0] == best_path[i+1][0]
        )
        logger.info(
            f"Found path with {len(result_path)} stations, {changes} changes, "
            f"total weight: {best_weight:.2f}"
        )
        
        return result_path

    def route_with_strategy(
        self,
        start_stop: str,
        end_stop: str,
        strategy: RoutingStrategy,
        context: Dict[str, Any]
    ) -> list:
        """
        Find route using a pluggable routing strategy with natural change minimization.
        
        Args:
            start_stop: Source station ID
            end_stop: Destination station ID
            strategy: RoutingStrategy instance defining optimization objective
            context: Context dictionary with:
                - 'current_time': datetime object
                - 'crowding_data': Station crowding metrics
                - 'user_preferences': User weightings (including max_changes)
                - 'predictor': DisruptionPredictor instance
                
        Returns:
            List of station IDs representing the path
        """
        # Extract max_changes from user preferences
        max_changes = context.get('user_preferences', {}).get('max_changes')
        
        # Use state-space graph approach for natural change penalization
        path = self.find_path_with_change_penalty(
            start_stop,
            end_stop,
            strategy=strategy,
            context=context,
            max_changes=max_changes
        )
        
        logger.info(
            f"Route found using {strategy.name} strategy: {len(path)} stops"
        )
        return path

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