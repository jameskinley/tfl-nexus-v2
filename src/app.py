from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from data.models import *
from data.data_ingest import DataIngestCommand
from data.tfl_client import TflClient
from data.database import get_db, init_db, SessionLocal
from data.mapper import ModelMapper
from data import db_models
import logging
from datetime import datetime
from difflib import get_close_matches
from graph.graph_visualiser import GraphVisualiser
from graph.graph_manager import GraphManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = FastAPI()
tfl_client = TflClient()

# Track ingestion status
ingestion_status = {
    "running": False,
    "started_at": None,
    "completed_at": None,
    "status": "idle",
    "message": None,
    "error": None
}

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()
    logging.info("Database initialized")

@app.get("/")
async def root() -> Response:
    return Response(status="success", message="health is wealth")

def run_ingestion_task():
    """Background task for data ingestion"""
    global ingestion_status
    
    db_session = SessionLocal()
    try:
        ingestion_status["running"] = True
        ingestion_status["status"] = "running"
        ingestion_status["started_at"] = datetime.now().isoformat()
        ingestion_status["message"] = "Ingestion in progress..."
        ingestion_status["error"] = None
        
        logging.info("Starting background ingestion task")
        command = DataIngestCommand()
        result = command.execute(db_session=db_session)
        
        ingestion_status["running"] = False
        ingestion_status["status"] = "completed"
        ingestion_status["completed_at"] = datetime.now().isoformat()
        ingestion_status["message"] = result.message
        
        logging.info("Background ingestion task completed successfully")
        
    except Exception as e:
        ingestion_status["running"] = False
        ingestion_status["status"] = "failed"
        ingestion_status["completed_at"] = datetime.now().isoformat()
        ingestion_status["error"] = str(e)
        ingestion_status["message"] = f"Ingestion failed: {str(e)}"
        logging.error(f"Background ingestion task failed: {e}", exc_info=True)
        
    finally:
        db_session.close()


@app.post("/route/ingest")
async def ingest_data(background_tasks: BackgroundTasks):
    """
    Start TfL data ingestion as a background task.
    This prevents timeout issues. Use GET /route/ingest/status to check progress.
    """
    global ingestion_status
    
    if ingestion_status["running"]:
        return {
            "status": "already_running",
            "message": "Ingestion is already in progress. Check /route/ingest/status for details."
        }
    
    # Reset status
    ingestion_status["completed_at"] = None
    ingestion_status["error"] = None
    
    # Start background task
    background_tasks.add_task(run_ingestion_task)
    
    return {
        "status": "started",
        "message": "Data ingestion started in background. Check /route/ingest/status for progress."
    }


@app.get("/route/ingest/status")
async def get_ingestion_status():
    """
    Get the current status of the data ingestion process.
    """
    return ingestion_status

def find_closest_station(query: str, session: Session, cutoff: float = 0.2, graph_manager: Optional[GraphManager] = None) -> Optional[db_models.Station]:
    """
    Find the closest matching station by name using fuzzy string matching.
    
    Args:
        query: Station name to search for
        session: Database session
        cutoff: Minimum similarity score (0-1) to consider a match
        graph_manager: Optional GraphManager. If provided, only returns stations that are in the graph.
        
    Returns:
        Closest matching Station or None if no good match found
    """
    all_stations = session.query(db_models.Station).all()
    
    if not all_stations:
        return None
    
    station_map: dict[str, db_models.Station] = {}
    station_name_list: list[str] = []
    
    for station in all_stations:
        # If graph_manager provided, only include stations that are in the graph
        if graph_manager and not graph_manager.graph.has_node(station.id):
            continue
            
        name_str = str(station.name)
        station_map[name_str] = station
        station_name_list.append(name_str)
    
    matches = get_close_matches(query, station_name_list, n=1, cutoff=cutoff)
    
    if matches:
        return station_map[matches[0]]
    
    return None


@app.get("/route/{from_location}/{to_location}")
async def get_route(from_location: str, to_location: str, time: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Calculate shortest route from one station to another using the tube network graph.
    
    Path Parameters:
    - from_location: Starting station name (fuzzy matching supported)
    - to_location: Destination station name (fuzzy matching supported)
    
    Query Parameters:
    - current_time: Optional time in HH:MM format for time-aware routing (default: None for static routing)
    
    Returns route with list of stations and travel details.
    """
    logger = logging.getLogger("route_calculation")

    if not time:
        time = datetime.now().strftime("%H:%M")

    try:
        # Build graph first
        graph_manager = GraphManager()
        graph_manager.build_graph_from_db(db)
        
        logger.info(f"Graph has {graph_manager.graph.number_of_nodes()} nodes")
        logger.info(f"Finding route from '{from_location}' to '{to_location}' at time {time}")
        
        # Find closest stations that are actually IN the graph
        from_station = find_closest_station(from_location, db, graph_manager=graph_manager)
        
        if not from_station:
            raise HTTPException(
                status_code=404, 
                detail=f"Could not find connected station matching '{from_location}'. Please try a different search term."
            )
        
        logger.info(f"Matched from_location to station: {from_station.id} {from_station.name}")
        
        to_station = find_closest_station(to_location, db, graph_manager=graph_manager)
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
                    detail=f"No route found between '{from_station.name}' and '{to_station.name}'"
                )
            raise
        
        route_stations = []
        total_time = 0.0
        
        for i, station_id in enumerate(path):
            station_data = graph_manager.graph.nodes[station_id]
            
            segment_time = 0.0
            segment_line = None
            segment_mode = None
            
            if i < len(path) - 1:
                next_station_id = path[i + 1]
                edge_data = graph_manager.graph[station_id][next_station_id]
                segment_time = edge_data.get('time_distance', 0.0)
                segment_line = edge_data.get('line')
                segment_mode = edge_data.get('mode')
                total_time += segment_time
            
            route_stations.append({
                "station_id": station_id,
                "station_name": station_data.get('name'),
                "lat": station_data.get('lat'),
                "lon": station_data.get('lon'),
                "ordinal": i,
                "time_to_next": segment_time if i < len(path) - 1 else 0.0,
                "line": segment_line,
                "mode": segment_mode
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
            "current_time": time
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error calculating route: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error calculating route: {str(e)}")

@app.get("/line")
async def get_all_lines(db: Session = Depends(get_db)):
    """
    Gets all available lines from the database.
    Use /route/ingest first to populate the database.
    """
    try:
        db_lines = db.query(db_models.Line).all()
        
        if not db_lines:
            return {
                "message": "No lines found in database. Please call /route/ingest first.",
                "lines": []
            }
        
        # Convert DB models to API models
        mapper = ModelMapper(session=db)
        api_lines = [mapper.db_line_to_api(line, include_routes=False) for line in db_lines]
        
        return {"lines": api_lines, "count": len(api_lines)}
    
    except Exception as e:
        logging.error(f"Error fetching lines: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/line/{line_id}")
async def get_line_details(line_id: str, db: Session = Depends(get_db)):
    """
    Gets details for a specific line, including routes and timetable information.
    """
    try:
        db_line = db.query(db_models.Line).filter(db_models.Line.id == line_id).first()
        
        if not db_line:
            raise HTTPException(status_code=404, detail=f"Line {line_id} not found")
        
        # Convert to API model with routes
        mapper = ModelMapper(session=db)
        api_line = mapper.db_line_to_api(db_line, include_routes=True)
        
        return api_line
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching line details: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/line/{line_id}/live-disruptions")
async def get_line_disruptions(line_id: str):
    """
    Gets live disruption information for a specific line from TfL API.
    """
    try:
        lines = tfl_client.get_lines_with_disruptions()
        
        for line in lines:
            if line.id == line_id:
                return {"line_id": line_id, "disruptions": line.disruptions}
        
        raise HTTPException(status_code=404, detail=f"Line {line_id} not found")
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching disruptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/meta/disruption-categories")
async def get_disruption_categories() -> list[str]:
    """
    Gets all valid disruption categories from TfL API.
    """
    return tfl_client.get_valid_disruption_categories()

@app.get("/meta/modes")
async def get_modes():
    """
    Gets all transport modes from the API.
    """
    return tfl_client.get_valid_modes()

@app.get("/station/search")
async def search_stations(q: str, limit: int = 10, db: Session = Depends(get_db)):
    """
    Search for stations by name.
    
    Query Parameters:
    - q: Search query string (case-insensitive)
    - limit: Maximum number of results to return (default: 10, max: 100)
    """
    try:
        # Validate limit
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
        
        if not q or q.strip() == "":
            raise HTTPException(status_code=400, detail="Search query cannot be empty")
        
        # Search stations by name (case-insensitive)
        db_stations = db.query(db_models.Station)\
            .filter(db_models.Station.name.ilike(f"%{q}%"))\
            .limit(limit)\
            .all()
        
        # Convert to API models
        mapper = ModelMapper(session=db)
        api_stations = [mapper.db_station_to_api(station) for station in db_stations]
        
        return {
            "stations": api_stations,
            "count": len(api_stations),
            "query": q
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error searching stations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_database_stats(db: Session = Depends(get_db)):
    """
    Get statistics about the data in the database.
    """
    try:
        line_count = db.query(db_models.Line).count()
        route_count = db.query(db_models.Route).count()
        station_count = db.query(db_models.Station).count()
        schedule_count = db.query(db_models.Schedule).count()
        
        return {
            "lines": line_count,
            "routes": route_count,
            "stations": station_count,
            "schedules": schedule_count
        }
    except Exception as e:
        logging.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/graph/stats")
async def get_graph_stats(db: Session = Depends(get_db)):
    """
    Build graph from database and return statistics.
    """
    try:
        from graph.graph_manager import GraphManager
        
        graph_manager = GraphManager()
        graph = graph_manager.build_graph_from_db(db)
        
        # Calculate statistics (avg degree = 2 * edges / nodes for undirected graph)
        avg_degree = 0.0
        if graph.number_of_nodes() > 0:
            avg_degree = (2 * graph.number_of_edges()) / graph.number_of_nodes()
        
        return {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "average_degree": round(avg_degree, 2),
            "connected_components": len(list(graph.connected_components())) if hasattr(graph, 'connected_components') else 1 #type:ignore
        }
    except Exception as e:
        logging.error(f"Error building graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/graph/visualize")
async def visualize_graph(db: Session = Depends(get_db)):
    """
    Generate and return a visualization of the transport network graph.
    Returns a PNG image of the graph.
    """
    try:
        graph_manager = GraphManager()
        graph = graph_manager.build_graph_from_db(db)
        visualiser = GraphVisualiser(graph)
        buf = visualiser.draw()

        return StreamingResponse(buf, media_type="image/png")
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error visualizing graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/stops/all")
async def get_all_stops(db: Session = Depends(get_db)):
    """
    Load all stops from the Tfl API.
    """
    return tfl_client.get_stop_points_by_mode()

@app.get("/graph/station/{station_name}")
async def check_station_in_graph(station_name: str, db: Session = Depends(get_db)):
    """
    Check if a station exists in the graph by name.
    Uses fuzzy matching to find the closest station match.
    
    Path Parameters:
    - station_name: Station name to search for (fuzzy matching supported)
    
    Returns station details and graph connectivity information.
    """
    try:
        # Find closest matching station in database (don't filter by graph)
        station = find_closest_station(station_name, db, graph_manager=None)
        
        if not station:
            raise HTTPException(
                status_code=404,
                detail=f"Could not find station matching '{station_name}'. Please try a different search term."
            )
        
        # Build graph and check if station is in it
        graph_manager = GraphManager()
        graph_manager.build_graph_from_db(db)
        
        # Check if station has any intervals
        interval_count = db.query(db_models.StationInterval).filter(db_models.StationInterval.station_id == station.id).count()
        
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
            # Add graph-specific information
            node_data = graph_manager.graph.nodes[station.id]
            neighbors = list(graph_manager.graph.neighbors(station.id))
            neighbor_names = [graph_manager.graph.nodes[n]['name'] for n in neighbors]
            
            response["graph_info"] = {
                "connected_stations": len(neighbors),
                "neighbors": neighbor_names[:10],  # Limit to first 10 neighbors
                "lines": node_data.get('lines', []),
                "modes": node_data.get('modes', [])
            }
            
            if len(neighbors) == 0:
                response["warning"] = "Station is in graph but has no connections (isolated node)"
        else:
            # Check if there's a similar station that IS in the graph
            connected_station = find_closest_station(station_name, db, graph_manager=graph_manager)
            if connected_station and connected_station.id != station.id:
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
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error checking station in graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error checking station: {str(e)}")