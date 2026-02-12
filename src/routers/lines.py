from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from data.database import get_db
from commands.line_operations import LineOperationsCommand
import logging

router = APIRouter(prefix="/lines", tags=["lines"])


@router.get("")
async def get_all_lines(db: Session = Depends(get_db)):
    """
    Get all available transport lines from the database.
    
    Retrieves a list of all transport lines (tube, overground, DLR, etc.) currently
    stored in the database. If no lines are found, indicates that data ingestion 
    needs to be performed first.
    
    Args:
        db: Database session dependency.
    
    Returns:
        dict: List of lines with their details and total count.
    """
    try:
        command = LineOperationsCommand(db)
        return command.get_all_lines()
    except Exception as e:
        logging.error(f"Error fetching lines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{line_id}")
async def get_line_details(line_id: str, db: Session = Depends(get_db)):
    """
    Get detailed information for a specific transport line.
    
    Retrieves comprehensive details for a single line including its routes,
    timetable information, and associated stations.
    
    Args:
        line_id: The unique identifier for the line (e.g., 'central', 'northern').
        db: Database session dependency.
    
    Returns:
        dict: Detailed line information including routes and schedules.
    
    Raises:
        HTTPException: 404 if line not found, 500 on server error.
    """
    try:
        command = LineOperationsCommand(db)
        return command.get_line_details(line_id)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching line details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{line_id}/disruptions")
async def get_line_disruptions(line_id: str, db: Session = Depends(get_db)):
    """
    Get live disruption information for a specific line from TfL API.
    
    Fetches real-time disruption data directly from the Transport for London API,
    including service closures, delays, and planned engineering works.
    
    Args:
        line_id: The unique identifier for the line (e.g., 'central', 'northern').
        db: Database session dependency.
    
    Returns:
        dict: Current disruptions affecting the specified line.
    
    Raises:
        HTTPException: 404 if line not found, 500 on server error.
    """
    try:
        command = LineOperationsCommand(db)
        return command.get_line_disruptions(line_id)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching disruptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
