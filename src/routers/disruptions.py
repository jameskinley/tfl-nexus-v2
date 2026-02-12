from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from data.database import get_db
from data import db_models
import logging

router = APIRouter(prefix="/disruptions", tags=["disruptions"])


@router.get("")
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


@router.get("/{line_id}")
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
