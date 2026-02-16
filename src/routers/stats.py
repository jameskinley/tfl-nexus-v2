from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from data.database import get_db
from commands.stats_operations import StatsOperationsCommand
import logging

router = APIRouter(prefix="/stats", tags=["Stats"])


@router.get(
    "",
    summary="Get Database Statistics",
    status_code=200,
    responses={
        200: {
            "description": "Successfully retrieved database statistics",
            "content": {
                "application/json": {
                    "example": {
                        "lines_count": 11,
                        "routes_count": 30,
                        "stations_count": 250,
                        "schedules_count": 1500,
                        "disruptions_count": 5,
                        "last_updated": "2026-02-16T10:30:00"
                    }
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
async def get_database_statistics(db: Session = Depends(get_db)):
    """
    Get comprehensive statistics about the data stored in the database.
    
    Retrieves counts of all major entities in the database including lines, routes,
    stations, and schedules. Useful for monitoring data completeness and system health.
    
    Args:
        db: Database session dependency.
    
    Returns:
        dict: Count of lines, routes, stations, and schedules in the database.
    
    Raises:
        HTTPException: 500 on server error.
    """
    try:
        command = StatsOperationsCommand(db)
        return command.get_database_stats()
    except Exception as e:
        logging.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
