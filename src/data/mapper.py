"""
Mapper between API models (models.py) and Database models (db_models.py)
Provides bidirectional conversion for DTO pattern
"""
from typing import Optional
from uuid import uuid4
from sqlalchemy.orm import Session
from . import models as api
from . import db_models as db
from logging import getLogger

logger = getLogger(__name__)


class ModelMapper:
    """Handles conversion between API and Database models"""

    def __init__(self, session: Optional[Session] = None):
        self.session = session
        self._mode_cache: dict[str, db.Mode] = {}
        self._line_cache: dict[str, db.Line] = {}
        self._station_cache: dict[str, db.Station] = {}

    # ==================== API → DB ====================

    def api_mode_to_db(self, api_mode: api.Mode) -> db.Mode:
        """Convert API Mode to DB Mode"""
        if api_mode.name in self._mode_cache:
            return self._mode_cache[api_mode.name]
        
        db_mode = db.Mode(
            name=api_mode.name,
            isTflService=api_mode.isTflService,
            isScheduledService=api_mode.isScheduledService
        )
        self._mode_cache[api_mode.name] = db_mode
        return db_mode

    def api_line_to_db(self, api_line: api.Line, include_routes: bool = True) -> db.Line:
        """Convert API Line to DB Line"""
        if api_line.id in self._line_cache:
            return self._line_cache[api_line.id]
        
        db_line = db.Line(
            id=api_line.id,
            name=api_line.name,
            mode_name=api_line.mode.name
        )
        
        # Ensure mode exists
        if self.session:
            existing_mode = self.session.query(db.Mode).filter_by(name=api_line.mode.name).first()
            if not existing_mode:
                db_mode = self.api_mode_to_db(api_line.mode)
                self.session.add(db_mode)
        
        self._line_cache[api_line.id] = db_line
        
        # Convert routes if requested
        if include_routes and api_line.routes:
            for api_route in api_line.routes:
                db_route = self.api_route_to_db(api_route, api_line)
                db_line.routes.append(db_route)
        
        return db_line

    def api_route_to_db(self, api_route: api.Route, api_line: api.Line) -> db.Route:
        """Convert API Route to DB Route"""
        db_route = db.Route(
            route_id=api_route.route_id,
            name=api_route.route_id,  # Use route_id as name if not provided
            line_id=api_line.id
        )
        
        # Convert station intervals (RouteNodes)
        for route_node in api_route.route:
            station = self._get_or_create_station(route_node.stop_name, route_node.stop_naptan)
            
            interval = db.StationInterval(
                station=station,  # Set relationship directly instead of station_id
                ordinal=route_node.ordinal,
                time_to_arrival=route_node.transition_time
            )
            db_route.station_intervals.append(interval)
            
            # Associate station with line mode
            if api_line.mode.name not in [m.name for m in station.modes]:
                mode = self.api_mode_to_db(api_line.mode)
                station.modes.append(mode)
        
        return db_route

    def _get_or_create_station(self, name: str, naptan: str) -> db.Station:
        """Get existing station or create new one"""
        # Check cache first
        if name in self._station_cache:
            station = self._station_cache[name]
            # Add naptan if not already present
            if naptan and not any(n.naptan_code == naptan for n in station.naptans):
                station.naptans.append(db.StationNaptan(naptan_code=naptan))
            return station
        
        # Check database if session available
        if self.session:
            station = self.session.query(db.Station).filter_by(name=name).first()
            if station:
                self._station_cache[name] = station
                if naptan and not any(n.naptan_code == naptan for n in station.naptans):
                    station.naptans.append(db.StationNaptan(naptan_code=naptan))
                return station
        
        # Create new station
        station = db.Station(
            id=uuid4().hex,
            name=name
        )
        if naptan:
            station.naptans.append(db.StationNaptan(naptan_code=naptan))
        
        self._station_cache[name] = station
        return station

    def add_timetable_to_route(
        self,
        db_route: db.Route,
        timetable_data: dict
    ):
        """
        Add timetable data to a DB Route
        
        Expected timetable_data format:
        {
            "schedules": [
                {
                    "name": "Monday - Thursday",
                    "firstJourney": {"hour": "05", "minute": "30"},
                    "lastJourney": {"hour": "23", "minute": "45"},
                    "periods": [
                        {
                            "fromTime": {"hour": "07", "minute": "00"},
                            "toTime": {"hour": "09", "minute": "30"},
                            "frequency": {"lowestFrequency": 3, "highestFrequency": 5}
                        }
                    ],
                    "knownJourneys": [
                        {"hour": "05", "minute": "30", "intervalId": 0}
                    ]
                }
            ],
            "stationIntervals": [
                {
                    "id": "0",
                    "intervals": [
                        {"stopId": "940GZZLUASG", "timeToArrival": 0.0},
                        {"stopId": "940GZZLUBBB", "timeToArrival": 2.5}
                    ]
                }
            ]
        }
        """
        # Process schedules
        if "schedules" in timetable_data:
            for sched_data in timetable_data["schedules"]:
                schedule = db.Schedule(
                    name=sched_data.get("name", "Unknown"),
                    first_journey_time=self._time_to_minutes(sched_data.get("firstJourney")),
                    last_journey_time=self._time_to_minutes(sched_data.get("lastJourney"))
                )
                
                # Add periods
                for period_data in sched_data.get("periods", []):
                    period = db.Period(
                        period_type=period_data.get("type", "Normal"),
                        from_time=self._time_to_minutes(period_data.get("fromTime")),
                        to_time=self._time_to_minutes(period_data.get("toTime")),
                        frequency_min=period_data.get("frequency", {}).get("highestFrequency"),
                        frequency_max=period_data.get("frequency", {}).get("lowestFrequency")
                    )
                    schedule.periods.append(period)
                
                # Add known journeys
                for journey_data in sched_data.get("knownJourneys", []):
                    journey = db.KnownJourney(
                        departure_time=self._time_to_minutes(journey_data),
                        interval_id=journey_data.get("intervalId")
                    )
                    schedule.known_journeys.append(journey)
                
                db_route.schedules.append(schedule)
        
        # Update station intervals with timing data
        if "stationIntervals" in timetable_data:
            interval_map = {}
            for interval_data in timetable_data["stationIntervals"]:
                interval_id = interval_data.get("id")
                interval_map[interval_id] = interval_data.get("intervals", [])
            
            # Update existing station intervals with timing
            for station_interval in db_route.station_intervals:
                # Safety check: ensure station is loaded
                if not station_interval.station:
                    logger.warning(f"Station not loaded for interval at ordinal {station_interval.ordinal}")
                    continue
                
                # Find matching interval data by station naptan
                for interval_id, intervals in interval_map.items():
                    for interval in intervals:
                        # Match by naptan code
                        station_naptans = [n.naptan_code for n in station_interval.station.naptans]
                        if interval.get("stopId") in station_naptans:
                            station_interval.time_to_arrival = interval.get("timeToArrival", 0.0)
                            break

    @staticmethod
    def _time_to_minutes(time_dict: Optional[dict]) -> Optional[float]:
        """Convert time dict {hour: str, minute: str} to minutes from midnight"""
        if not time_dict:
            return None
        try:
            hour = int(time_dict.get("hour", 0))
            minute = int(time_dict.get("minute", 0))
            return hour * 60 + minute
        except (ValueError, TypeError):
            return None

    # ==================== DB → API ====================

    def db_mode_to_api(self, db_mode: db.Mode) -> api.Mode:
        """Convert DB Mode to API Mode"""
        return api.Mode(
            name=str(db_mode.name),
            isTflService=bool(db_mode.isTflService),
            isScheduledService=bool(db_mode.isScheduledService)
        )

    def db_line_to_api(self, db_line: db.Line, include_routes: bool = False) -> api.Line:
        """Convert DB Line to API Line"""
        api_line = api.Line(
            id=str(db_line.id),
            name=str(db_line.name),
            mode=self.db_mode_to_api(db_line.mode),
            disruptions=[],  # Disruptions not stored in DB currently
            routes=[]
        )
        
        if include_routes:
            for db_route in db_line.routes:
                api_route = self.db_route_to_api(db_route)
                api_line.routes.append(api_route)
        
        return api_line

    def db_route_to_api(self, db_route: db.Route) -> api.Route:
        """Convert DB Route to API Route"""
        route_nodes = []
        
        for interval in sorted(db_route.station_intervals, key=lambda x: x.ordinal):
            route_node = api.RouteNode(
                ordinal=int(interval.ordinal),
                stop_name=str(interval.station.name),
                stop_naptan=str(interval.station.naptans[0].naptan_code) if interval.station.naptans else "",
                line=str(db_route.line_id),
                mode=str(db_route.line.mode_name),
                distance=0.0,  # Distance not stored in DB currently
                transition_time=float(interval.time_to_arrival) if interval.time_to_arrival else 0.0
            )
            route_nodes.append(route_node)
        
        return api.Route(
            route_id=str(db_route.route_id),
            route=route_nodes,
            robustness_score=0.0,
            modes_used=[db_route.line.mode_name],
            total_time=sum(rn.transition_time for rn in route_nodes),
            total_distance=0.0
        )
