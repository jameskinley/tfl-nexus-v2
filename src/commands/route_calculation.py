from sqlalchemy.orm import Session
from fastapi import HTTPException
from graph.graph_manager import GraphManager
from data import db_models
from difflib import get_close_matches
from typing import Optional
import logging


class RouteCalculationCommand:
    def __init__(self, db_session: Session):
        self.db_session = db_session
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

    def calculate_route(self, from_location: str, to_location: str, time: str) -> dict:
        graph_manager = GraphManager()
        graph_manager.build_graph_from_db_with_disruptions(self.db_session)
        
        self.logger.info(f"Graph has {graph_manager.graph.number_of_nodes()} nodes")
        self.logger.info(f"Finding route from '{from_location}' to '{to_location}' at time {time}")
        
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
        
        try:
            path = graph_manager.route_time_only(from_station.id, to_station.id, time)
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
        
        return {
            "status": "success",
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
