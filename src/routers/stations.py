from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from data.database import get_db
from commands.station_operations import StationOperationsCommand
import logging

router = APIRouter(prefix="/stations", tags=["stations"])


@router.get("/search")
async def search_stations(q: str, limit: int = 10, db: Session = Depends(get_db)):
    """
    Search for stations by name using case-insensitive partial matching.
    
    Performs a database search for stations whose names contain the query string.
    Supports pagination through the limit parameter.
    
    Args:
        q: Search query string (case-insensitive, partial match).
        limit: Maximum number of results to return (default: 10, max: 100).
        db: Database session dependency.
    
    Returns:
        dict: List of matching stations with their details, count, and the original query.
    
    Raises:
        HTTPException: 400 if query is empty or limit is invalid, 500 on server error.
    """
    try:
        command = StationOperationsCommand(db)
        return command.search_stations(q, limit)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error searching stations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{station_name}/graph-status")
async def check_station_in_graph(station_name: str, db: Session = Depends(get_db)):
    """
    Check if a station exists in the routing graph and get connectivity information.
    
    Uses fuzzy matching to find the closest station match and determines whether it's
    included in the routing graph. For stations in the graph, provides additional
    information about connected stations, available lines, and transport modes.
    
    Args:
        station_name: Station name to search for (fuzzy matching supported).
        db: Database session dependency.
    
    Returns:
        dict: Station details, graph inclusion status, connectivity information, and suggestions
              for similar connected stations if the queried station is not in the graph.
    
    Raises:
        HTTPException: 404 if no matching station found, 500 on server error.
    """
    try:
        command = StationOperationsCommand(db)
        return command.check_station_in_graph(station_name)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error checking station in graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error checking station: {str(e)}")
