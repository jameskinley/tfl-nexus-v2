from fastapi import APIRouter
from commands.meta_operations import MetaOperationsCommand
import logging

router = APIRouter(prefix="/meta", tags=["Meta"])


@router.get(
    "/disruption-categories",
    summary="Get Disruption Categories",
    status_code=200,
    response_model=list[str],
    responses={
        200: {
            "description": "Successfully retrieved disruption categories",
            "content": {
                "application/json": {
                    "example": [
                        "RealTime",
                        "PlannedWork",
                        "Information",
                        "Event",
                        "Crowding",
                        "StatusAlert"
                    ]
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to fetch categories from TfL API"}
                }
            }
        }
    }
)
async def get_disruption_categories() -> list[str]:
    """
    Get all valid disruption categories from the TfL API.
    
    Retrieves the comprehensive list of disruption category codes used by Transport
    for London to classify service disruptions (e.g., 'RealTime', 'PlannedWork',
    'Information').
    
    Returns:
        list[str]: List of valid disruption category codes.
    """
    command = MetaOperationsCommand()
    return command.get_disruption_categories()


@router.get(
    "/modes",
    summary="Get Transport Modes",
    status_code=200,
    responses={
        200: {
            "description": "Successfully retrieved transport modes",
            "content": {
                "application/json": {
                    "example": {
                        "modes": [
                            {
                                "id": "tube",
                                "name": "Tube",
                                "description": "London Underground services"
                            },
                            {
                                "id": "bus",
                                "name": "Bus",
                                "description": "London bus services"
                            },
                            {
                                "id": "overground",
                                "name": "Overground",
                                "description": "London Overground services"
                            },
                            {
                                "id": "dlr",
                                "name": "DLR",
                                "description": "Docklands Light Railway"
                            }
                        ],
                        "count": 4
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to fetch modes from TfL API"}
                }
            }
        }
    }
)
async def get_transport_modes():
    """
    Get all available transport modes from the TfL API.
    
    Retrieves a list of all transport modes supported by the TfL network including
    tube, bus, overground, dlr, tram, river, cable-car, etc.
    
    Returns:
        list: Available transport mode codes and descriptions.
    """
    command = MetaOperationsCommand()
    return command.get_modes()


@router.get(
    "/stops",
    summary="Get All Stop Points",
    status_code=200,
    responses={
        200: {
            "description": "Successfully retrieved all stop points",
            "content": {
                "application/json": {
                    "example": {
                        "tube": [
                            {
                                "id": "940GZZLUOXC",
                                "name": "Oxford Circus Underground Station",
                                "lat": 51.515224,
                                "lon": -0.141903
                            }
                        ],
                        "bus": [
                            {
                                "id": "490000001S",
                                "name": "Oxford Circus Station",
                                "lat": 51.515419,
                                "lon": -0.141848
                            }
                        ],
                        "total_stops": 2
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to fetch stops from TfL API"}
                }
            }
        }
    }
)
async def get_all_stops():
    """
    Get all stop points from the TfL API organized by transport mode.
    
    Fetches the complete list of stop points (stations, bus stops, etc.) from the
    Transport for London API, grouped by their respective transport modes.
    
    Returns:
        dict: Stop points organized by transport mode.
    """
    command = MetaOperationsCommand()
    return command.get_all_stops()
