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
        lines = self.tfl_client.get_lines_with_disruptions()
        
        for line in lines:
            if line.id == line_id:
                return {"line_id": line_id, "disruptions": line.disruptions}
        
        raise HTTPException(status_code=404, detail=f"Line {line_id} not found")
