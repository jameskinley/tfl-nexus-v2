from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from data.database import get_db
from commands.stats_operations import StatsOperationsCommand
from data.api_models import ResourceResponse, SystemStatisticsData
from data.hateoas import HateoasBuilder
import logging
from pydantic import BaseModel

router = APIRouter(prefix="/system", tags=["System"])
logger = logging.getLogger(__name__)


class HealthData(BaseModel):
    status: str
    message: str


@router.get(
    "/health",
    response_model=ResourceResponse[HealthData],
    summary="Health Check",
    status_code=200
)
async def health_check() -> ResourceResponse[HealthData]:
    health_data = HealthData(
        status="healthy",
        message="Service is operational"
    )
    
    links = HateoasBuilder.build_links("/system/health")
    
    return ResourceResponse(data=health_data, links=links)


@router.get(
    "/statistics",
    response_model=ResourceResponse[SystemStatisticsData],
    summary="Get System Statistics",
    status_code=200
)
async def get_system_statistics(
    db: Session = Depends(get_db)
) -> ResourceResponse[SystemStatisticsData]:
    try:
        command = StatsOperationsCommand(db)
        stats = command.get_database_stats()
        
        from data import db_models
        disruption_count = db.query(db_models.Disruption).filter(
            db_models.Disruption.is_active == True
        ).count()
        
        stats_data = SystemStatisticsData(
            lines=stats['lines'],
            routes=stats['routes'],
            stations=stats['stations'],
            schedules=stats['schedules'],
            disruptions=disruption_count,
            last_updated=None
        )
        
        self_href = "/system/statistics"
        links = HateoasBuilder.build_links(self_href)
        
        return ResourceResponse(data=stats_data, links=links)
    
    except Exception as e:
        logger.error(f"Error fetching system statistics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
