from sqlalchemy.orm import Session
from data.data_ingest import DataIngestCommand
from data.database import SessionLocal
from datetime import datetime
import logging


class IngestionOperationsCommand:
    def __init__(self):
        self.ingestion_status = {
            "running": False,
            "started_at": None,
            "completed_at": None,
            "status": "idle",
            "message": None,
            "error": None
        }

    def get_status(self) -> dict:
        return self.ingestion_status

    def is_running(self) -> bool:
        return self.ingestion_status["running"]

    def reset_completion(self):
        self.ingestion_status["completed_at"] = None
        self.ingestion_status["error"] = None

    def run_ingestion_task(self):
        db_session = SessionLocal()
        try:
            self.ingestion_status["running"] = True
            self.ingestion_status["status"] = "running"
            self.ingestion_status["started_at"] = datetime.now().isoformat()
            self.ingestion_status["message"] = "Ingestion in progress..."
            self.ingestion_status["error"] = None
            
            logging.info("Starting background ingestion task")
            command = DataIngestCommand()
            result = command.execute(db_session=db_session)
            
            self.ingestion_status["running"] = False
            self.ingestion_status["status"] = "completed"
            self.ingestion_status["completed_at"] = datetime.now().isoformat()
            self.ingestion_status["message"] = result.message
            
            logging.info("Background ingestion task completed successfully")
            
        except Exception as e:
            self.ingestion_status["running"] = False
            self.ingestion_status["status"] = "failed"
            self.ingestion_status["completed_at"] = datetime.now().isoformat()
            self.ingestion_status["error"] = str(e)
            self.ingestion_status["message"] = f"Ingestion failed: {str(e)}"
            logging.error(f"Background ingestion task failed: {e}", exc_info=True)
            
        finally:
            db_session.close()
