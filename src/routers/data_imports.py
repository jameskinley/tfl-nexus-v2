from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from data.database import get_db
from commands.ingestion_operations import IngestionOperationsCommand
from data.api_models import (
    ResourceResponse, CollectionResponse, DataImportJobData,
    CreateDataImportRequest, PaginationMeta
)
from data.hateoas import HateoasBuilder
import logging
import uuid

router = APIRouter(prefix="/data-imports", tags=["Data Imports"])
logger = logging.getLogger(__name__)

ingestion_command = IngestionOperationsCommand()


@router.post(
    "",
    response_model=ResourceResponse[DataImportJobData],
    summary="Start Data Import Job",
    status_code=201
)
async def create_data_import(
    request: CreateDataImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> ResourceResponse[DataImportJobData]:
    try:
        if ingestion_command.is_running():
            raise HTTPException(
                status_code=409,
                detail="Data import already in progress"
            )
        
        job_id = str(uuid.uuid4())
        ingestion_command.reset_completion()
        background_tasks.add_task(ingestion_command.run_ingestion_task)
        
        job_data = DataImportJobData(
            id=job_id,
            status="running",
            started_at=ingestion_command.get_status().get('started_at'),
            completed_at=None,
            error=None,
            progress_message="Data import started"
        )
        
        self_href = f"/data-imports/{job_id}"
        links = HateoasBuilder.build_links(self_href, method="GET")
        
        return ResourceResponse(data=job_data, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting data import: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "",
    response_model=CollectionResponse[DataImportJobData],
    summary="List Data Import Jobs",
    status_code=200
)
async def list_data_imports() -> CollectionResponse[DataImportJobData]:
    try:
        status = ingestion_command.get_status()
        
        job_data = DataImportJobData(
            id="current",
            status="running" if status['is_running'] else "completed",
            started_at=status.get('started_at'),
            completed_at=status.get('completed_at'),
            error=status.get('error'),
            progress_message=status.get('status')
        )
        
        jobs = [job_data]
        
        meta = PaginationMeta(
            total=len(jobs),
            count=len(jobs),
            page=1,
            per_page=len(jobs),
            total_pages=1
        )
        
        links = HateoasBuilder.build_links("/data-imports")
        
        return CollectionResponse(data=jobs, meta=meta, links=links)
    
    except Exception as e:
        logger.error(f"Error listing data imports: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{job_id}",
    response_model=ResourceResponse[DataImportJobData],
    summary="Get Data Import Job Status",
    status_code=200
)
async def get_data_import_status(job_id: str) -> ResourceResponse[DataImportJobData]:
    try:
        status = ingestion_command.get_status()
        
        job_data = DataImportJobData(
            id=job_id,
            status="running" if status['is_running'] else "completed",
            started_at=status.get('started_at'),
            completed_at=status.get('completed_at'),
            error=status.get('error'),
            progress_message=status.get('status')
        )
        
        self_href = f"/data-imports/{job_id}"
        links = HateoasBuilder.build_links(self_href)
        
        return ResourceResponse(data=job_data, links=links)
    
    except Exception as e:
        logger.error(f"Error fetching import job status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
