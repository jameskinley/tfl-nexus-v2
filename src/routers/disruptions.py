from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from data.database import get_db
from data import db_models
from data.api_models import (
    ResourceResponse, CollectionResponse, DisruptionData, 
    StationData, PaginationMeta
)
from data.hateoas import HateoasBuilder
from typing import Optional
import logging
import math

router = APIRouter(prefix="/disruptions", tags=["Disruptions"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    response_model=CollectionResponse[DisruptionData],
    summary="List All Disruptions",
    status_code=200
)
async def list_disruptions(
    active: bool = Query(True, description="Filter active disruptions only"),
    line_id: Optional[str] = Query(None, description="Filter by line ID"),
    category: Optional[str] = Query(None, description="Filter by disruption category"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    start_date: Optional[str] = Query(None, description="Filter disruptions from this date (ISO format)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
) -> CollectionResponse[DisruptionData]:
    try:
        query_builder = db.query(db_models.Disruption)
        
        if active:
            query_builder = query_builder.filter(db_models.Disruption.is_active == True)
        
        if line_id:
            query_builder = query_builder.filter(db_models.Disruption.line_id == line_id)
        
        if category:
            query_builder = query_builder.filter(db_models.Disruption.category == category)
        
        if start_date:
            query_builder = query_builder.filter(db_models.Disruption.created >= start_date)
        
        total = query_builder.count()
        total_pages = math.ceil(total / per_page) if total > 0 else 1
        
        offset = (page - 1) * per_page
        disruptions_db = query_builder.offset(offset).limit(per_page).all()
        
        disruptions = [
            DisruptionData(
                id=d.id,
                line_id=d.line_id,
                type=d.type,
                category=d.category,
                category_description=d.category_description,
                summary=d.summary,
                description=d.description,
                additional_info=d.additional_info,
                created=d.created,
                last_update=d.last_update,
                is_active=d.is_active,
                affected_stops_count=len(d.affected_stops)
            )
            for d in disruptions_db
        ]
        
        query_params = {}
        if not active:
            query_params['active'] = str(False)
        if line_id:
            query_params['line_id'] = line_id
        if category:
            query_params['category'] = category
        if start_date:
            query_params['start_date'] = start_date
        
        meta = PaginationMeta(
            total=total,
            count=len(disruptions),
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )
        
        links = HateoasBuilder.build_pagination_links(
            "/disruptions", page, per_page, total_pages, query_params
        )
        
        return CollectionResponse(data=disruptions, meta=meta, links=links)
    
    except Exception as e:
        logger.error(f"Error listing disruptions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{disruption_id}",
    response_model=ResourceResponse[DisruptionData],
    summary="Get Disruption Details",
    status_code=200
)
async def get_disruption(
    disruption_id: str = Path(..., description="Disruption ID"),
    db: Session = Depends(get_db)
) -> ResourceResponse[DisruptionData]:
    try:
        disruption = db.query(db_models.Disruption).filter(
            db_models.Disruption.id == disruption_id
        ).first()
        
        if not disruption:
            raise HTTPException(status_code=404, detail=f"Disruption '{disruption_id}' not found")
        
        disruption_data = DisruptionData(
            id=disruption.id,
            line_id=disruption.line_id,
            type=disruption.type,
            category=disruption.category,
            category_description=disruption.category_description,
            summary=disruption.summary,
            description=disruption.description,
            additional_info=disruption.additional_info,
            created=disruption.created,
            last_update=disruption.last_update,
            is_active=disruption.is_active,
            affected_stops_count=len(disruption.affected_stops)
        )
        
        self_href = f"/disruptions/{disruption_id}"
        additional_links = HateoasBuilder.disruption_links(disruption_id)
        links = HateoasBuilder.build_links(self_href, additional_links)
        
        return ResourceResponse(data=disruption_data, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching disruption: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{disruption_id}/affected-stations",
    response_model=CollectionResponse[StationData],
    summary="Get Stations Affected by Disruption",
    status_code=200
)
async def get_disruption_affected_stations(
    disruption_id: str = Path(..., description="Disruption ID"),
    db: Session = Depends(get_db)
) -> CollectionResponse[StationData]:
    try:
        disruption = db.query(db_models.Disruption).filter(
            db_models.Disruption.id == disruption_id
        ).first()
        
        if not disruption:
            raise HTTPException(status_code=404, detail=f"Disruption '{disruption_id}' not found")
        
        stations = [
            StationData(
                id=affected.station.id,
                name=affected.station.name,
                lat=affected.station.lat,
                lon=affected.station.lon,
                modes=[mode.name for mode in affected.station.modes]
            )
            for affected in disruption.affected_stops
        ]
        
        meta = PaginationMeta(
            total=len(stations),
            count=len(stations),
            page=1,
            per_page=len(stations),
            total_pages=1
        )
        
        links = HateoasBuilder.build_links(f"/disruptions/{disruption_id}/affected-stations")
        
        return CollectionResponse(data=stations, meta=meta, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching affected stations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
