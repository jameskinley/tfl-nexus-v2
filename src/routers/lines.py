from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from data.database import get_db
from data import db_models
from data.api_models import (
    ResourceResponse, CollectionResponse, LineData, 
    StationData, DisruptionData, PaginationMeta
)
from data.hateoas import HateoasBuilder
from typing import Optional
import logging
import math

router = APIRouter(prefix="/lines", tags=["Lines"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    response_model=CollectionResponse[LineData],
    summary="List All Lines",
    status_code=200
)
async def list_lines(
    mode: Optional[str] = Query(None, description="Filter by transport mode"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
) -> CollectionResponse[LineData]:
    try:
        query_builder = db.query(db_models.Line)
        
        if mode:
            query_builder = query_builder.filter(db_models.Line.mode_name == mode)
        
        total = query_builder.count()
        total_pages = math.ceil(total / per_page) if total > 0 else 1
        
        offset = (page - 1) * per_page
        db_lines = query_builder.offset(offset).limit(per_page).all()
        
        lines = [
            LineData(
                id=line.id,
                name=line.name,
                mode=line.mode.name
            )
            for line in db_lines
        ]
        
        query_params = {}
        if mode:
            query_params['mode'] = mode
        
        meta = PaginationMeta(
            total=total,
            count=len(lines),
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )
        
        links = HateoasBuilder.build_pagination_links(
            "/lines", page, per_page, total_pages, query_params
        )
        
        return CollectionResponse(data=lines, meta=meta, links=links)
    
    except Exception as e:
        logger.error(f"Error listing lines: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{line_id}",
    response_model=ResourceResponse[LineData],
    summary="Get Line Details",
    status_code=200
)
async def get_line(
    line_id: str = Path(..., description="Line ID"),
    db: Session = Depends(get_db)
) -> ResourceResponse[LineData]:
    try:
        db_line = db.query(db_models.Line).filter(
            db_models.Line.id == line_id
        ).first()
        
        if not db_line:
            raise HTTPException(status_code=404, detail=f"Line '{line_id}' not found")
        
        line_data = LineData(
            id=db_line.id,
            name=db_line.name,
            mode=db_line.mode.name
        )
        
        self_href = f"/lines/{line_id}"
        additional_links = HateoasBuilder.line_links(line_id)
        links = HateoasBuilder.build_links(self_href, additional_links)
        
        return ResourceResponse(data=line_data, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching line: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{line_id}/stations",
    response_model=CollectionResponse[StationData],
    summary="Get Stations on Line",
    status_code=200
)
async def get_line_stations(
    line_id: str = Path(..., description="Line ID"),
    db: Session = Depends(get_db)
) -> CollectionResponse[StationData]:
    try:
        db_line = db.query(db_models.Line).filter(
            db_models.Line.id == line_id
        ).first()
        
        if not db_line:
            raise HTTPException(status_code=404, detail=f"Line '{line_id}' not found")
        
        stations = [
            StationData(
                id=station.id,
                name=station.name,
                lat=station.lat,
                lon=station.lon,
                modes=[mode.name for mode in station.modes]
            )
            for station in db_line.stations
        ]
        
        meta = PaginationMeta(
            total=len(stations),
            count=len(stations),
            page=1,
            per_page=len(stations),
            total_pages=1
        )
        
        links = HateoasBuilder.build_links(f"/lines/{line_id}/stations")
        
        return CollectionResponse(data=stations, meta=meta, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching line stations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{line_id}/disruptions",
    response_model=CollectionResponse[DisruptionData],
    summary="Get Disruptions for Line",
    status_code=200
)
async def get_line_disruptions(
    line_id: str = Path(..., description="Line ID"),
    active: bool = Query(True, description="Filter active disruptions only"),
    db: Session = Depends(get_db)
) -> CollectionResponse[DisruptionData]:
    try:
        db_line = db.query(db_models.Line).filter(
            db_models.Line.id == line_id
        ).first()
        
        if not db_line:
            raise HTTPException(status_code=404, detail=f"Line '{line_id}' not found")
        
        query_builder = db.query(db_models.Disruption).filter(
            db_models.Disruption.line_id == line_id
        )
        
        if active:
            query_builder = query_builder.filter(db_models.Disruption.is_active == True)
        
        disruptions_db = query_builder.all()
        
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
        
        meta = PaginationMeta(
            total=len(disruptions),
            count=len(disruptions),
            page=1,
            per_page=len(disruptions),
            total_pages=1
        )
        
        links = HateoasBuilder.build_links(f"/lines/{line_id}/disruptions")
        
        return CollectionResponse(data=disruptions, meta=meta, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching line disruptions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
