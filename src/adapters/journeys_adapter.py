from mcp_provider import mcp
from data.database import SessionLocal
from data.api_models import ResourceResponse, JourneyData, JourneyRoute, RouteSegment, StationData
from commands.route_calculation import RouteCalculationCommand
from data.hateoas import HateoasBuilder
from datetime import datetime
from typing import Optional

@mcp.tool(
    name="plan_route",
    title="Plan Route Between Stations",
    description="Calculates the best route between two stations based on the specified strategy and parameters. Station names are fuzzy matched to the nearest valid station, so some level of imprecision is okay."
)
async def get_journey(
    origin: str,
    destination: str,
    time: Optional[str] = None,
    strategy: str = "fastest",
    alternatives: bool = False,
    max_changes: Optional[int] = None,
    accessible: bool = False,
    avoid_lines: Optional[str] = None
) -> ResourceResponse[JourneyData]:
    db = SessionLocal()
    if not time:
        time = datetime.now().strftime("%H:%M")
    try:
        command = RouteCalculationCommand(db, routing_mode=strategy)
        result = command.calculate_route(
            origin, destination, time,
            alternatives=alternatives,
            max_changes=max_changes,
            accessible=accessible,
            avoid_lines=[line.strip() for line in avoid_lines.split(',')] if avoid_lines else None
        )
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
                line=station_data.get('line'),
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
    finally:
        db.close()
