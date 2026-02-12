from fastapi import APIRouter, HTTPException
from commands.meta_operations import MetaOperationsCommand
import logging

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/disruption-categories")
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


@router.get("/modes")
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


@router.get("/stops")
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
