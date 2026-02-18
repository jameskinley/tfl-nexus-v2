from sqlalchemy.orm import Session
from fastapi import HTTPException
from data import db_models
from data.mapper import ModelMapper
from data.tfl_client import TflClient
import logging


class LineOperationsCommand:
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.mapper = ModelMapper(session=db_session)
        self.tfl_client = TflClient()

    def get_all_lines(self) -> dict:
        db_lines = self.db_session.query(db_models.Line).all()
        
        if not db_lines:
            return {
                "message": "No lines found in database. Please call /route/ingest first.",
                "lines": []
            }
        
        api_lines = [self.mapper.db_line_to_api(line, include_routes=False) for line in db_lines]
        
        return {"lines": api_lines, "count": len(api_lines)}

    def get_line_details(self, line_id: str):
        db_line = self.db_session.query(db_models.Line).filter(db_models.Line.id == line_id).first()
        
        if not db_line:
            raise HTTPException(status_code=404, detail=f"Line {line_id} not found")
        
        api_line = self.mapper.db_line_to_api(db_line, include_routes=True)
        return api_line

    def get_line_disruptions(self, line_id: str) -> dict:
        db_line = self.db_session.query(db_models.Line).filter(db_models.Line.id == line_id).first()
        
        if not db_line:
            raise HTTPException(status_code=404, detail=f"Line {line_id} not found")
        
        disruptions = self.db_session.query(db_models.Disruption).filter(
            db_models.Disruption.line_id == line_id,
            db_models.Disruption.is_active == True
        ).all()
        
        return {
            "line_id": line_id,
            "disruptions": [{
                "id": d.id,
                "type": d.type,
                "category": d.category,
                "category_description": d.category_description,
                "summary": d.summary,
                "description": d.description,
                "additional_info": d.additional_info,
                "created": d.created,
                "last_update": d.last_update
            } for d in disruptions]
        }
