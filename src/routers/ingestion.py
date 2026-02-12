from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from data.database import get_db
from commands.ingestion_operations import IngestionOperationsCommand
import logging

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

ingestion_command = IngestionOperationsCommand()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


@router.post("/start")
async def start_data_ingestion(background_tasks: BackgroundTasks):
    """
    Start TfL data ingestion as a background task.
    
    This endpoint initiates the data ingestion process from the Transport for London (TfL) API.
    The ingestion runs in the background to prevent timeout issues. Use GET /ingestion/status 
    to check progress and completion status.
    
    Returns:
        dict: Status message indicating whether ingestion started or is already running.
    """
    if ingestion_command.is_running():
        return {
            "status": "already_running",
            "message": "Ingestion is already in progress. Check /ingestion/status for details."
        }
    
    ingestion_command.reset_completion()
    background_tasks.add_task(ingestion_command.run_ingestion_task)
    
    return {
        "status": "started",
        "message": "Data ingestion started in background. Check /ingestion/status for progress."
    }


@router.get("/status")
async def get_ingestion_status():
    """
    Get the current status of the data ingestion process.
    
    Returns detailed information about the ingestion task including whether it's running,
    when it started, completion time, and any error messages if the task failed.
    
    Returns:
        dict: Ingestion status with running state, timestamps, status message, and error info.
    """
    return ingestion_command.get_status()
