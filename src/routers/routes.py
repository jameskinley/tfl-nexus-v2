from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from data.database import get_db
from commands.route_calculation import RouteCalculationCommand
from graph.routing_strategies import list_available_strategies
from datetime import datetime
from typing import Optional
import logging

router = APIRouter(prefix="/routes", tags=["Routing"])


@router.get(
    "/strategies",
    summary="List Available Routing Strategies",
    status_code=200,
    responses={
        200: {
            "description": "Successfully retrieved routing strategies",
            "content": {
                "application/json": {
                    "example": {
                        "strategies": [
                            {
                                "name": "fastest",
                                "description": "Minimize travel time",
                                "priority": "speed"
                            },
                            {
                                "name": "robust",
                                "description": "Prefer reliable routes avoiding disruption-prone lines",
                                "priority": "reliability"
                            },
                            {
                                "name": "low_crowding",
                                "description": "Avoid crowded stations and lines",
                                "priority": "comfort"
                            },
                            {
                                "name": "ml_hybrid",
                                "description": "Balanced optimization using machine learning",
                                "priority": "balanced"
                            }
                        ]
                    }
                }
            }
        }
    }
)
async def get_strategies():
    """
    List available routing strategies.
    
    Returns:
        list: Available routing strategies with descriptions
    """
    return {
        "strategies": list_available_strategies()
    }


@router.get(
    "/{from_location}/{to_location}",
    summary="Calculate Optimal Route",
    status_code=200,
    responses={
        200: {
            "description": "Successfully calculated route",
            "content": {
                "application/json": {
                    "example": {
                        "routing_mode": "fastest",
                        "from_station": "King's Cross St. Pancras",
                        "to_station": "Oxford Circus",
                        "matched_from": "Kings Cross St Pancras Underground Station",
                        "matched_to": "Oxford Circus Underground Station",
                        "route": [
                            {
                                "station": "King's Cross St. Pancras",
                                "line": "victoria",
                                "arrival_time": "10:30",
                                "departure_time": "10:30",
                                "wait_time_minutes": 0
                            },
                            {
                                "station": "Oxford Circus",
                                "line": "victoria",
                                "arrival_time": "10:38",
                                "departure_time": "10:38",
                                "wait_time_minutes": 0
                            }
                        ],
                        "total_time_minutes": 8,
                        "total_stops": 2,
                        "changes": 0,
                        "has_disruptions": False,
                        "disruption_warnings": []
                    }
                }
            }
        },
        400: {
            "description": "Invalid request parameters",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_mode": {
                            "summary": "Invalid routing mode",
                            "value": {"detail": "Invalid routing mode. Use: fastest, robust, low_crowding, or ml_hybrid"}
                        },
                        "no_route": {
                            "summary": "No route exists",
                            "value": {"detail": "No route found between stations"}
                        }
                    }
                }
            }
        },
        404: {
            "description": "Station not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Station 'invalid' not found"}
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Route calculation failed"}
                }
            }
        }
    }
)
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
