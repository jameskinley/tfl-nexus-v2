from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from data.database import get_db
from commands.route_calculation import RouteCalculationCommand
from graph.routing_strategies import list_available_strategies
from datetime import datetime
from typing import Optional
import logging

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("/strategies")
async def get_strategies():
    """
    List available routing strategies.
    
    Returns:
        list: Available routing strategies with descriptions
    """
    return {
        "strategies": list_available_strategies()
    }


@router.get("/{from_location}/{to_location}")
async def calculate_route(
    from_location: str, 
    to_location: str, 
    time: Optional[str] = None,
    mode: str = Query("fastest", description="Routing mode: fastest, robust, low_crowding, ml_hybrid"),
    alternatives: bool = Query(False, description="Include alternative routes"),
    db: Session = Depends(get_db)
):
    """
    Calculate optimal route from one station to another using various optimization strategies.
    
    This endpoint supports multiple routing modes:
    - fastest: Minimize travel time (default)
    - robust: Prefer reliable routes, avoiding disruption-prone lines
    - low_crowding: Avoid crowded stations and lines
    - ml_hybrid: Balanced optimization of time, reliability, and crowding
    
    Station names support fuzzy matching, so exact spelling is not required.
    
    Args:
        from_location: Starting station name (fuzzy matching supported).
        to_location: Destination station name (fuzzy matching supported).
        time: Optional time in HH:MM format for time-aware routing (defaults to current time).
        mode: Routing optimization mode (fastest/robust/low_crowding/ml_hybrid).
        alternatives: Whether to include alternative routes using different strategies.
        db: Database session dependency.
    
    Returns:
        dict: Route information including:
            - routing_mode: Strategy used
            - matched stations
            - route: List of stations with timing and line details
            - total_time_minutes: Total journey time
            - has_disruptions: Whether route encounters disruptions
            - alternatives: (if requested) Alternative routes
    
    Raises:
        HTTPException: 404 if stations cannot be found, 400 if no route exists or invalid mode,
                       500 if route calculation fails.
    """
    if not time:
        time = datetime.now().strftime("%H:%M")

    try:
        command = RouteCalculationCommand(db, routing_mode=mode)
        return command.calculate_route(from_location, to_location, time, alternatives=alternatives)
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error calculating route: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error calculating route: {str(e)}")
