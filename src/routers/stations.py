from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from data.database import get_db
from data import db_models
from data.mapper import ModelMapper
from data.api_models import (
    ResourceResponse, CollectionResponse, StationData, 
    LineData, CrowdingData, PaginationMeta
)
from data.hateoas import HateoasBuilder
from graph.graph_manager import GraphManager
from commands.crowding_operations import CrowdingOperations
from typing import Optional
import logging
import math

router = APIRouter(prefix="/stations", tags=["Stations"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    response_model=CollectionResponse[StationData],
    summary="List or Search Stations",
    status_code=200
)
async def list_stations(
    q: Optional[str] = Query(None, description="Search query for station name"),
    line_id: Optional[str] = Query(None, description="Filter by line ID"),
    mode: Optional[str] = Query(None, description="Filter by transport mode"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
) -> CollectionResponse[StationData]:
    try:
        query_builder = db.query(db_models.Station)
        
        if q:
            query_builder = query_builder.filter(db_models.Station.name.ilike(f"%{q}%"))
        
        if line_id:
            query_builder = query_builder.join(db_models.Station.lines).filter(
                db_models.Line.id == line_id
            )
        
        if mode:
            query_builder = query_builder.join(db_models.Station.modes).filter(
                db_models.Mode.name == mode
            )
        
        total = query_builder.count()
        total_pages = math.ceil(total / per_page) if total > 0 else 1
        
        offset = (page - 1) * per_page
        db_stations = query_builder.offset(offset).limit(per_page).all()
        
        stations = [
            StationData(
                id=station.id,
                name=station.name,
                lat=station.lat,
                lon=station.lon,
                modes=[mode.name for mode in station.modes]
            )
            for station in db_stations
        ]
        
        query_params = {}
        if q:
            query_params['q'] = q
        if line_id:
            query_params['line_id'] = line_id
        if mode:
            query_params['mode'] = mode
        
        meta = PaginationMeta(
            total=total,
            count=len(stations),
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )
        
        links = HateoasBuilder.build_pagination_links(
            "/stations", page, per_page, total_pages, query_params
        )
        
        return CollectionResponse(data=stations, meta=meta, links=links)
    
    except Exception as e:
        logger.error(f"Error listing stations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{station_id}",
    response_model=ResourceResponse[StationData],
    summary="Get Station Details",
    status_code=200
)
async def get_station(
    station_id: str = Path(..., description="Station ID or name"),
    db: Session = Depends(get_db)
) -> ResourceResponse[StationData]:
    try:
        db_station = db.query(db_models.Station).filter(
            db_models.Station.id == station_id
        ).first()
        
        if not db_station:
            db_station = db.query(db_models.Station).filter(
                db_models.Station.name.ilike(f"%{station_id}%")
            ).first()
        
        if not db_station:
            raise HTTPException(status_code=404, detail=f"Station '{station_id}' not found")
        
        station_data = StationData(
            id=db_station.id,
            name=db_station.name,
            lat=db_station.lat,
            lon=db_station.lon,
            modes=[mode.name for mode in db_station.modes]
        )
        
        self_href = f"/stations/{station_id}"
        additional_links = HateoasBuilder.station_links(db_station.id)
        links = HateoasBuilder.build_links(self_href, additional_links)
        
        return ResourceResponse(data=station_data, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching station: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{station_id}/lines",
    response_model=CollectionResponse[LineData],
    summary="Get Lines Serving Station",
    status_code=200
)
async def get_station_lines(
    station_id: str = Path(..., description="Station ID"),
    db: Session = Depends(get_db)
) -> CollectionResponse[LineData]:
    try:
        db_station = db.query(db_models.Station).filter(
            db_models.Station.id == station_id
        ).first()
        
        if not db_station:
            raise HTTPException(status_code=404, detail=f"Station '{station_id}' not found")
        
        lines = [
            LineData(
                id=line.id,
                name=line.name,
                mode=line.mode.name
            )
            for line in db_station.lines
        ]
        
        meta = PaginationMeta(
            total=len(lines),
            count=len(lines),
            page=1,
            per_page=len(lines),
            total_pages=1
        )
        
        links = HateoasBuilder.build_links(f"/stations/{station_id}/lines")
        
        return CollectionResponse(data=lines, meta=meta, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching station lines: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{station_id}/crowding",
    response_model=CollectionResponse[CrowdingData],
    summary="Get Station Crowding Data",
    status_code=200
)
async def get_station_crowding(
    station_id: str = Path(..., description="Station ID"),
    db: Session = Depends(get_db)
) -> CollectionResponse[CrowdingData]:
    try:
        db_station = db.query(db_models.Station).filter(
            db_models.Station.id == station_id
        ).first()
        
        if not db_station:
            raise HTTPException(status_code=404, detail=f"Station '{station_id}' not found")
        
        crowding_records = db.query(db_models.StationCrowding).filter(
            db_models.StationCrowding.station_id == station_id
        ).order_by(db_models.StationCrowding.timestamp.desc()).limit(20).all()
        
        crowding_data_list = [
            CrowdingData(
                station_id=record.station_id,
                line_id=record.line_id,
                crowding_level=record.crowding_level,
                capacity_percentage=record.capacity_percentage,
                timestamp=record.timestamp,
                lat=db_station.lat,
                lon=db_station.lon
            )
            for record in crowding_records
        ]
        
        meta = PaginationMeta(
            total=len(crowding_data_list),
            count=len(crowding_data_list),
            page=1,
            per_page=len(crowding_data_list),
            total_pages=1
        )
        
        links = HateoasBuilder.build_links(f"/stations/{station_id}/crowding")
        
        return CollectionResponse(data=crowding_data_list, meta=meta, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching station crowding: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{station_id}/connections",
    response_model=CollectionResponse[StationData],
    summary="Get Connected Stations",
    status_code=200
)
async def get_station_connections(
    station_id: str = Path(..., description="Station ID"),
    db: Session = Depends(get_db)
) -> CollectionResponse[StationData]:
    try:
        db_station = db.query(db_models.Station).filter(
            db_models.Station.id == station_id
        ).first()
        
        if not db_station:
            raise HTTPException(status_code=404, detail=f"Station '{station_id}' not found")
        
        graph_manager = GraphManager()
        graph_manager.build_graph_from_db_with_disruptions(db)
        
        if not graph_manager.graph.has_node(station_id):
            raise HTTPException(
                status_code=404, 
                detail=f"Station '{station_id}' not found in routing graph"
            )
        
        neighbors = list(graph_manager.graph.neighbors(station_id))
        
        connected_stations = []
        for neighbor_id in neighbors:
            neighbor_station = db.query(db_models.Station).filter(
                db_models.Station.id == neighbor_id
            ).first()
            
            if neighbor_station:
                connected_stations.append(StationData(
                    id=neighbor_station.id,
                    name=neighbor_station.name,
                    lat=neighbor_station.lat,
                    lon=neighbor_station.lon,
                    modes=[mode.name for mode in neighbor_station.modes]
                ))
        
        meta = PaginationMeta(
            total=len(connected_stations),
            count=len(connected_stations),
            page=1,
            per_page=len(connected_stations),
            total_pages=1
        )
        
        links = HateoasBuilder.build_links(f"/stations/{station_id}/connections")
        
        return CollectionResponse(data=connected_stations, meta=meta, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching station connections: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
