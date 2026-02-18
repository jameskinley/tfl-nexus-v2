from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from data.database import get_db
from commands.route_calculation import RouteCalculationCommand
from graph.routing_strategies import list_available_strategies
from data.api_models import (
    ResourceResponse, CollectionResponse, JourneyData, JourneyRoute, 
    RouteSegment, StationData, RoutingStrategyData
)
from data.hateoas import HateoasBuilder
from datetime import datetime
from typing import Optional
import logging

router = APIRouter(prefix="/journeys", tags=["Journeys"])
logger = logging.getLogger(__name__)


@router.get(
    "/{origin}/to/{destination}",
    response_model=ResourceResponse[JourneyData],
    summary="Get Journey Between Stations",
    status_code=200
)
async def get_journey(
    origin: str,
    destination: str,
    time: Optional[str] = Query(None, description="Time in HH:MM format or ISO 8601"),
    strategy: str = Query("fastest", pattern="^(fastest|robust|low_crowding|ml_hybrid)$"),
    alternatives: bool = Query(False, description="Include alternative route strategies"),
    max_changes: Optional[int] = Query(None, ge=0, le=5, description="Maximum number of line changes"),
    accessible: bool = Query(False, description="Wheelchair accessible routes only"),
    avoid_lines: Optional[str] = Query(None, description="Comma-separated line IDs to avoid"),
    db: Session = Depends(get_db)
) -> ResourceResponse[JourneyData]:
    if not time:
        time = datetime.now().strftime("%H:%M")
    
    try:
        command = RouteCalculationCommand(db, routing_mode=strategy)
        result = command.calculate_route(origin, destination, time, alternatives=alternatives)
        
        origin_station = StationData(
            id=result['from']['station_id'],
            name=result['from']['matched'],
            modes=[]
        )
        
        destination_station = StationData(
            id=result['to']['station_id'],
            name=result['to']['matched'],
            modes=[]
        )
        
        segments = []
        for station_data in result['route']:
            segment = RouteSegment(
                station=StationData(
                    id=station_data['station_id'],
                    name=station_data['station_name'],
                    lat=station_data.get('lat'),
                    lon=station_data.get('lon'),
                    modes=[]
                ),
                line=station_data.get('line', ''),
                arrival_time=None,
                departure_time=None,
                wait_time_minutes=station_data.get('time_to_next', 0.0)
            )
            segments.append(segment)
        
        changes = 0
        current_line = None
        for seg in segments:
            if seg.line and current_line and seg.line != current_line:
                changes += 1
            if seg.line:
                current_line = seg.line
        
        primary_route = JourneyRoute(
            total_time_minutes=result['total_time_minutes'],
            total_stops=result['total_stations'],
            changes=changes,
            segments=segments,
            has_disruptions=result['has_disruptions'],
            disruption_warnings=[]
        )
        
        journey_data = JourneyData(
            origin=origin_station,
            destination=destination_station,
            requested_time=time,
            strategy=strategy,
            primary_route=primary_route,
            alternatives=[]
        )
        
        self_href = f"/journeys/{origin}/to/{destination}?time={time}&strategy={strategy}"
        additional_links = HateoasBuilder.journey_links(origin_station.id, destination_station.id)
        links = HateoasBuilder.build_links(self_href, additional_links)
        
        return ResourceResponse(data=journey_data, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating journey: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error calculating journey: {str(e)}")


@router.get(
    "",
    response_model=CollectionResponse[RoutingStrategyData],
    summary="List Available Routing Strategies",
    status_code=200
)
async def list_routing_strategies() -> CollectionResponse[RoutingStrategyData]:
    strategies_raw = list_available_strategies()
    
    strategies = [
        RoutingStrategyData(
            name=s['name'],
            description=s['description'],
            priority=s['priority']
        )
        for s in strategies_raw
    ]
    
    from data.api_models import PaginationMeta
    meta = PaginationMeta(
        total=len(strategies),
        count=len(strategies),
        page=1,
        per_page=len(strategies),
        total_pages=1
    )
    
    links = HateoasBuilder.build_links("/journeys")
    
    return CollectionResponse(data=strategies, meta=meta, links=links)
