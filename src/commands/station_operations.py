from sqlalchemy.orm import Session
from fastapi import HTTPException
from data import db_models
from data.mapper import ModelMapper
from graph.graph_manager import GraphManager
from difflib import get_close_matches
from typing import Optional


class StationOperationsCommand:
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.mapper = ModelMapper(session=db_session)

    def search_stations(self, query: str, limit: int = 10) -> dict:
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
        
        if not query or query.strip() == "":
            raise HTTPException(status_code=400, detail="Search query cannot be empty")
        
        db_stations = self.db_session.query(db_models.Station)\
            .filter(db_models.Station.name.ilike(f"%{query}%"))\
            .limit(limit)\
            .all()
        
        api_stations = [self.mapper.db_station_to_api(station) for station in db_stations]
        
        return {
            "stations": api_stations,
            "count": len(api_stations),
            "query": query
        }

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

    def check_station_in_graph(self, station_name: str) -> dict:
        station = self.find_closest_station(station_name, graph_manager=None)
        
        if not station:
            raise HTTPException(
                status_code=404,
                detail=f"Could not find station matching '{station_name}'. Please try a different search term."
            )
        
        graph_manager = GraphManager()
        graph_manager.build_graph_from_db_with_disruptions(self.db_session)
        
        interval_count = self.db_session.query(db_models.StationInterval)\
            .filter(db_models.StationInterval.station_id == station.id).count()
        
        in_graph = graph_manager.graph.has_node(station.id)
        
        response = {
            "query": station_name,
            "matched_station": {
                "id": station.id,
                "name": station.name,
                "lat": station.lat,
                "lon": station.lon
            },
            "in_graph": in_graph,
            "has_route_data": interval_count > 0
        }
        
        if in_graph:
            node_data = graph_manager.graph.nodes[station.id]
            neighbors = list(graph_manager.graph.neighbors(station.id))
            neighbor_names = [graph_manager.graph.nodes[n]['name'] for n in neighbors]
            
            response["graph_info"] = {
                "connected_stations": len(neighbors),
                "neighbors": neighbor_names[:10],
                "lines": node_data.get('lines', []),
                "modes": node_data.get('modes', [])
            }
            
            if len(neighbors) == 0:
                response["warning"] = "Station is in graph but has no connections (isolated node)"
        else:
            connected_station = self.find_closest_station(station_name, graph_manager=graph_manager)
            if connected_station and str(connected_station.id) != str(station.id):
                response["suggestion"] = {
                    "message": "Found a connected station with similar name",
                    "station": {
                        "id": connected_station.id,
                        "name": connected_station.name,
                        "lat": connected_station.lat,
                        "lon": connected_station.lon
                    }
                }
            response["error"] = "Station exists in database but is not in the graph (no route intervals)"
        
        return response
