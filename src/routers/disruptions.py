from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from data.database import get_db
from data import db_models
import logging

router = APIRouter(prefix="/disruptions", tags=["Disruptions"])


@router.get(
    "",
    summary="Get All Active Disruptions",
    status_code=200,
    responses={
        200: {
            "description": "Successfully retrieved active disruptions",
            "content": {
                "application/json": {
                    "example": {
                        "disruptions": [
                            {
                                "id": 1,
                                "line_id": "central",
                                "type": "lineInfo",
                                "category": "RealTime",
                                "category_description": "Real-time information",
                                "summary": "Minor delays",
                                "description": "Central Line: Minor delays due to a faulty train",
                                "additional_info": "Tickets will be accepted on local buses",
                                "created": "2026-02-16T10:30:00",
                                "last_update": "2026-02-16T10:45:00",
                                "affected_stops_count": 5
                            }
                        ],
                        "count": 1
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Database connection failed"}
                }
            }
        }
    }
)
async def get_all_active_disruptions(db: Session = Depends(get_db)):
    """
    Get all currently active disruptions from the database.
    
    Returns disruptions that are affecting the transport network, including
    information about affected lines and stops.
    
    Args:
        db: Database session dependency.
    
    Returns:
        dict: List of active disruptions with details.
    """
    try:
        disruptions = db.query(db_models.Disruption).filter(
            db_models.Disruption.is_active == True
        ).all()
        
        result = []
        for d in disruptions:
            result.append({
                "id": d.id,
                "line_id": d.line_id,
                "type": d.type,
                "category": d.category,
                "category_description": d.category_description,
                "summary": d.summary,
                "description": d.description,
                "additional_info": d.additional_info,
                "created": d.created,
                "last_update": d.last_update,
                "affected_stops_count": len(d.affected_stops)
            })
        
        return {"disruptions": result, "count": len(result)}
    
    except Exception as e:
        logging.error(f"Error fetching disruptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{line_id}",
    summary="Get Disruptions by Line",
    status_code=200,
    responses={
        200: {
            "description": "Successfully retrieved line disruptions",
            "content": {
                "application/json": {
                    "example": {
                        "line_id": "central",
                        "disruptions": [
                            {
                                "id": 1,
                                "type": "lineInfo",
                                "category": "RealTime",
                                "summary": "Minor delays",
                                "description": "Central Line: Minor delays due to a faulty train",
                                "last_update": "2026-02-16T10:45:00"
                            }
                        ],
                        "count": 1
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Database query error"}
                }
            }
        }
    }
)
async def get_disruptions_by_line(line_id: str, db: Session = Depends(get_db)):
    """
    Get active disruptions for a specific line.
    
    Args:
        line_id: The unique identifier for the line.
        db: Database session dependency.
    
    Returns:
        dict: List of disruptions affecting the specified line.
    """
    try:
        disruptions = db.query(db_models.Disruption).filter(
            db_models.Disruption.line_id == line_id,
            db_models.Disruption.is_active == True
        ).all()
        
        result = []
        for d in disruptions:
            result.append({
                "id": d.id,
                "type": d.type,
                "category": d.category,
                "summary": d.summary,
                "description": d.description,
                "last_update": d.last_update
            })
        
        return {"line_id": line_id, "disruptions": result, "count": len(result)}
    
    except Exception as e:
        logging.error(f"Error fetching disruptions for line {line_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
