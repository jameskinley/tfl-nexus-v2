from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from data.database import get_db
from commands.station_operations import StationOperationsCommand
import logging

router = APIRouter(prefix="/stations", tags=["Stations"])


@router.get(
    "/search",
    summary="Search Stations",
    status_code=200,
    responses={
        200: {
            "description": "Successfully retrieved matching stations",
            "content": {
                "application/json": {
                    "example": {
                        "query": "king",
                        "stations": [
                            {
                                "id": 1,
                                "name": "King's Cross St. Pancras",
                                "latitude": 51.5308,
                                "longitude": -0.1238,
                                "modes": ["tube", "national-rail"]
                            },
                            {
                                "id": 2,
                                "name": "Kingsbury",
                                "latitude": 51.5843,
                                "longitude": -0.2786,
                                "modes": ["tube"]
                            }
                        ],
                        "count": 2
                    }
                }
            }
        },
        400: {
            "description": "Invalid request parameters",
            "content": {
                "application/json": {
                    "example": {"detail": "Query string 'q' is required"}
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Database query failed"}
                }
            }
        }
    }
)
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


@router.get(
    "/{station_name}/graph-status",
    summary="Check Station Graph Status",
    status_code=200,
    responses={
        200: {
            "description": "Successfully retrieved station graph status",
            "content": {
                "application/json": {
                    "examples": {
                        "in_graph": {
                            "summary": "Station is in routing graph",
                            "value": {
                                "station_name": "King's Cross St. Pancras",
                                "matched_station": "Kings Cross St Pancras Underground Station",
                                "in_graph": True,
                                "connected_stations": [
                                    "Euston",
                                    "Angel",
                                    "Caledonian Road"
                                ],
                                "available_lines": ["northern", "piccadilly", "victoria", "circle"],
                                "transport_modes": ["tube"]
                            }
                        },
                        "not_in_graph": {
                            "summary": "Station not in routing graph",
                            "value": {
                                "station_name": "Example Station",
                                "matched_station": "Example Station",
                                "in_graph": False,
                                "reason": "Station not included in routing network",
                                "suggestions": [
                                    "Nearby Station 1",
                                    "Nearby Station 2"
                                ]
                            }
                        }
                    }
                }
            }
        },
        404: {
            "description": "Station not found",
            "content": {
                "application/json": {
                    "example": {"detail": "No station found matching 'invalid'"}
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to build graph"}
                }
            }
        }
    }
)
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
