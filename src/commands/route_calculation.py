from sqlalchemy.orm import Session
from fastapi import HTTPException
from graph.graph_manager import GraphManager
from graph.routing_strategies import get_strategy, list_available_strategies
from data import db_models
from data.disruption_analyzer import DisruptionPredictor
from commands.crowding_polling import CrowdingPollingCommand
from difflib import get_close_matches
from typing import Optional
from datetime import datetime
import logging


class RouteCalculationCommand:
    def __init__(self, db_session: Session, routing_mode: str = 'fastest'):
        self.db_session = db_session
        self.routing_mode = routing_mode
        self.logger = logging.getLogger("route_calculation")

    def find_closest_station(
        self, 
        query: str, 
        cutoff: float = 0.2, 
        graph_manager: Optional[GraphManager] = None
    ) -> Optional[db_models.Station]:
        all_stations = self.db_session.query(db_models.Station).all()
        
        if not all_stations:
            return None
        
        station_map: dict[str, db_models.Station] = {}
        station_name_list: list[str] = []
        
        for station in all_stations:
            if graph_manager and not graph_manager.graph.has_node(station.id):
                continue
                
            name_str = str(station.name)
            station_map[name_str] = station
            station_name_list.append(name_str)
        
        matches = get_close_matches(query, station_name_list, n=1, cutoff=cutoff)
        
        if matches:
            return station_map[matches[0]]
        
        return None

    def calculate_route(
        self, 
        from_location: str, 
        to_location: str, 
        time: str, 
        alternatives: bool = False,
        max_changes: Optional[int] = None,
        accessible: bool = False,
        avoid_lines: Optional[list[str]] = None
    ) -> dict:
        graph_manager = GraphManager()
        graph_manager.build_graph_from_db_with_disruptions(self.db_session)
        
        self.logger.info(f"Graph has {graph_manager.graph.number_of_nodes()} nodes")
        self.logger.info(f"Finding route from '{from_location}' to '{to_location}' at time {time} using {self.routing_mode} mode")
        
        from_station = self.find_closest_station(from_location, graph_manager=graph_manager)
        
        if not from_station:
            raise HTTPException(
                status_code=404, 
                detail=f"Could not find connected station matching '{from_location}'. Please try a different search term."
            )
        
        self.logger.info(f"Matched from_location to station: {from_station.id} {from_station.name}")
        
        to_station = self.find_closest_station(to_location, graph_manager=graph_manager)
        if not to_station:
            raise HTTPException(
                status_code=404,
                detail=f"Could not find connected station matching '{to_location}'. Please try a different search term."
            )
        
        if str(from_station.id) == str(to_station.id):
            raise HTTPException(
                status_code=400,
                detail="Origin and destination stations are the same"
            )
        
        # Prepare routing strategy and context
        try:
            strategy = get_strategy(self.routing_mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Build context for strategy
        context = {
            'current_time': datetime.strptime(time, "%H:%M") if time else datetime.now(),
            'crowding_data': {},
            'user_preferences': {
                'max_changes': max_changes,
                'accessible': accessible,
                'avoid_lines': avoid_lines or []
            },
            'predictor': None
        }
        
        # Apply fragility scores for robust/ml_hybrid modes
        if self.routing_mode in ['robust', 'ml_hybrid']:
            predictor = DisruptionPredictor(self.db_session)
            context['predictor'] = predictor
            graph_manager.apply_fragility_scores(self.db_session, predictor)
        
        # Apply crowding penalties for low_crowding/ml_hybrid modes
        if self.routing_mode in ['low_crowding', 'ml_hybrid']:
            crowding_command = CrowdingPollingCommand(self.db_session)
            recent_crowding = crowding_command.get_recent_crowding(minutes=30)
            
            # Convert to format expected by graph manager
            crowding_data = {}
            for record in recent_crowding:
                if record.station_id not in crowding_data:
                    crowding_data[record.station_id] = {}
                if record.line_id not in crowding_data[record.station_id]:
                    crowding_data[record.station_id][record.line_id] = []
                
                crowding_data[record.station_id][record.line_id].append({
                    'crowding_level': record.crowding_level,
                    'capacity_percentage': record.capacity_percentage or 0.0,
                    'time_slice': record.time_slice or 'unknown'
                })
            
            context['crowding_data'] = crowding_data
            graph_manager.apply_crowding_penalties(crowding_data)
        
        # Calculate route using strategy
        try:
            if self.routing_mode == 'fastest':
                # Use existing time-only routing for fastest mode
                path = graph_manager.route_time_only(
                    str(from_station.id), 
                    str(to_station.id), 
                    time,
                    max_changes=max_changes
                )
            else:
                # Use strategy-based routing
                path = graph_manager.route_with_strategy(
                    str(from_station.id),
                    str(to_station.id),
                    strategy,
                    context
                )
        except Exception as e:
            if "not in" in str(e) or "NetworkXNoPath" in str(type(e).__name__):
                raise HTTPException(
                    status_code=400,
                    detail=f"No route found between '{from_station.name}' and '{to_station.name}'. This may be due to service disruptions."
                )
            raise
        
        route_stations = []
        total_time = 0.0
        has_disruptions = False
        
        for i, station_id in enumerate(path):
            station_data = graph_manager.graph.nodes[station_id]
            
            segment_time = 0.0
            segment_line = None
            segment_mode = None
            segment_disrupted = False
            
            if i < len(path) - 1:
                next_station_id = path[i + 1]
                edge_data = graph_manager.graph[station_id][next_station_id]
                segment_time = edge_data.get('time_distance', 0.0)
                segment_line = edge_data.get('line')
                segment_mode = edge_data.get('mode')
                segment_disrupted = edge_data.get('disrupted', False)
                if segment_disrupted:
                    has_disruptions = True
                total_time += segment_time
            
            route_stations.append({
                "station_id": station_id,
                "station_name": station_data.get('name'),
                "lat": station_data.get('lat'),
                "lon": station_data.get('lon'),
                "ordinal": i,
                "time_to_next": segment_time if i < len(path) - 1 else 0.0,
                "line": segment_line,
                "mode": segment_mode,
                "disrupted": segment_disrupted
            })
        
        result = {
            "status": "success",
            "routing_mode": self.routing_mode,
            "from": {
                "query": from_location,
                "matched": from_station.name,
                "station_id": from_station.id
            },
            "to": {
                "query": to_location,
                "matched": to_station.name,
                "station_id": to_station.id
            },
            "route": route_stations,
            "total_stations": len(route_stations),
            "total_time_minutes": round(total_time, 2),
            "current_time": time,
            "has_disruptions": has_disruptions
        }
        
        # Add alternatives if requested
        if alternatives:
            result['alternatives'] = self._calculate_alternatives(
                from_station, to_station, time, graph_manager
            )
        
        return result
    
    def _calculate_alternatives(self, from_station, to_station, time, graph_manager):
        """Calculate alternative routes using different strategies."""
        alternatives = []
        
        # Try other routing modes
        other_modes = ['fastest', 'robust', 'low_crowding']
        if self.routing_mode in other_modes:
            other_modes.remove(self.routing_mode)
        
        for mode in other_modes[:2]:  # Limit to 2 alternatives
            try:
                alt_command = RouteCalculationCommand(self.db_session, routing_mode=mode)
                alt_result = alt_command.calculate_route(from_station.name, to_station.name, time, alternatives=False)
                alternatives.append({
                    'mode': mode,
                    'total_time_minutes': alt_result['total_time_minutes'],
                    'total_stations': alt_result['total_stations'],
                    'has_disruptions': alt_result['has_disruptions']
                })
            except Exception as e:
                self.logger.warning(f"Failed to calculate {mode} alternative: {e}")
        
        return alternatives
