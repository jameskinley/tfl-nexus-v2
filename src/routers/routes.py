from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from data.database import get_db
from commands.route_calculation import RouteCalculationCommand
from datetime import datetime
from typing import Optional
import logging

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("/{from_location}/{to_location}")
async def calculate_route(
    from_location: str, 
    to_location: str, 
    time: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    """
    Calculate shortest route from one station to another using the tube network graph.
    
    This endpoint uses Dijkstra's algorithm on a weighted graph of the transport network
    to find the optimal route between two stations. Station names support fuzzy matching,
    so exact spelling is not required.
    
    Args:
        from_location: Starting station name (fuzzy matching supported).
        to_location: Destination station name (fuzzy matching supported).
        time: Optional time in HH:MM format for time-aware routing (defaults to current time).
        db: Database session dependency.
    
    Returns:
        dict: Route information including matched stations, list of stations along the route,
              total travel time, and details about each segment (line, mode, time).
    
    Raises:
        HTTPException: 404 if stations cannot be found, 400 if no route exists or stations are identical,
                       500 if route calculation fails.
    """
    if not time:
        time = datetime.now().strftime("%H:%M")

    try:
        command = RouteCalculationCommand(db)
        return command.calculate_route(from_location, to_location, time)
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error calculating route: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error calculating route: {str(e)}")
