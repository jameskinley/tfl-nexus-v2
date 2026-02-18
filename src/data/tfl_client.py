from logging import getLogger
from dotenv import load_dotenv
from . import constants
import os
from datetime import datetime

from requests import request
from tqdm import tqdm

from .models import *

load_dotenv()


class TflClient:
    """
    Client for interacting with Transport for London (TfL) API.
    
    Provides methods to fetch lines, routes, timetables, and stop points.
    """

    def __init__(self):
        self.base_url = "https://api.tfl.gov.uk"
        self.app_key = os.getenv("TFL_PRIMARY_KEY")
        self._logger = getLogger(__name__)

    def get_valid_disruption_categories(self) -> list[str]:
        URL = "/Line/Meta/DisruptionCategories"

        response = self._make_request("GET", URL)

        self._logger.info(f"Received response from TFL API: {response}")

        return response

    def get_valid_modes(self) -> list[Mode]:
        URL = "/Line/Meta/Modes"

        response = self._make_request("GET", URL)

        self._logger.debug(f"Received response from TFL API: {response}")

        return [Mode(
            name=res["modeName"],
            isTflService=res["isTflService"],
            isScheduledService=res["isScheduledService"]) for res in response if res["modeName"] not in ["taxi", "river-bus", "bus", "coach", "cycle", "cycle-hire", "river-tour", "cable-car"]]
            #lowkenuinely the best way to get rid of these modes :)

    def get_timetable(self, line_id: str, origin_stop: str):
        URL = f"/Line/{line_id}/Timetable/{origin_stop}"

        response = self._make_request("GET", URL)

        self._logger.info(f"Received timetable response from TFL API for {line_id} at {origin_stop}")

        return response

    def parse_timetable(self, response: dict) -> dict:
        """
        Parse timetable API response into structured format
        
        Returns dict with:
        {
            "schedules": [list of schedule data],
            "stationIntervals": [list of station interval data]
        }
        """
        parsed = {
            "schedules": [],
            "stationIntervals": []
        }

        if not response or "timetable" not in response:
            self._logger.warning("No timetable data in response")
            return parsed

        timetable = response["timetable"]
        
        # Parse routes (contains schedules and station intervals)
        for route in timetable.get("routes", []):
            # Extract station intervals
            for station_interval in route.get("stationIntervals", []):
                parsed["stationIntervals"].append({
                    "id": station_interval.get("id"),
                    "intervals": station_interval.get("intervals", [])
                })
            
            # Extract schedules
            for schedule in route.get("schedules", []):
                schedule_data = {
                    "name": schedule.get("name", "Unknown"),
                    "firstJourney": schedule.get("firstJourney"),
                    "lastJourney": schedule.get("lastJourney"),
                    "periods": schedule.get("periods", []),
                    "knownJourneys": schedule.get("knownJourneys", [])
                }
                parsed["schedules"].append(schedule_data)

        return parsed

    def get_timetable_for_route(self, line_id: str, origin_stops: list[str]) -> dict:
        """
        Fetch and parse timetables for multiple route origins
        
        Args:
            line_id: The line identifier
            origin_stops: List of NaPTAN codes for route origins
            
        Returns:
            Combined timetable data from all origins
        """
        combined_data = {
            "schedules": [],
            "stationIntervals": []
        }

        for origin in origin_stops:
            try:
                self._logger.info(f"Fetching timetable for {line_id} from {origin}")
                response = self.get_timetable(line_id, origin)
                parsed = self.parse_timetable(response)
                
                # Merge schedules (avoiding duplicates by name)
                existing_schedule_names = {s["name"] for s in combined_data["schedules"]}
                for schedule in parsed["schedules"]:
                    if schedule["name"] not in existing_schedule_names:
                        combined_data["schedules"].append(schedule)
                        existing_schedule_names.add(schedule["name"])
                
                # Merge station intervals (avoiding duplicates by id)
                existing_interval_ids = {si["id"] for si in combined_data["stationIntervals"]}
                for interval in parsed["stationIntervals"]:
                    if interval["id"] not in existing_interval_ids:
                        combined_data["stationIntervals"].append(interval)
                        existing_interval_ids.add(interval["id"])
                        
            except Exception as e:
                self._logger.error(f"Failed to fetch timetable for {line_id} from {origin}: {e}")
                continue

        return combined_data

    def get_lines_with_routes(self, modes: list[str] = []) -> list[Line]:
        URL = f"/Line/Mode/{','.join(modes)}/Route"

        response = self._make_request("GET", URL)

        mode_collection = self.get_valid_modes()
        mode_dict = {mode.name: mode for mode in mode_collection}
        lines: dict[str, Line] = {}

        for res in response:
            line = Line(
                id=res["id"],
                name=res["name"],
                mode=mode_dict[res["modeName"]],
                disruptions=[],
            )
            lines[line.id] = line

        for line_id in lines.keys():
            URL = f"/Line/{line_id}/Route/Sequence/all"
            response = self._make_request("GET", URL)

            for route in response["orderedLineRoutes"]:
                route_name = route["name"]
                lines[line_id].routes.append(Route(
                    route_id=route_name,
                    route=[RouteNode(
                        ordinal=idx,
                        stop_name=stop,
                        stop_naptan=stop,
                        line=line_id,
                        mode=lines[line_id].mode.name,
                        distance=0,
                        transition_time=0
                    ) for idx, stop in enumerate(route["naptanIds"])]
                ))

        return list(lines.values())
    
    def get_stop_points_by_mode(self, modes: list[str] | None = None) -> list[Station]:
        if modes is None:
            modes = constants.VALID_MODES
        
        URL = f"/StopPoint/Mode/{','.join(modes)}"

        response = self._make_request("GET", URL)

        stops: dict[str, Station] = {}

        for stop in tqdm(response["stopPoints"], desc="Processing stops", unit="stop"):
            if stop["commonName"] in stops.keys():
                stop_obj = stops[stop["commonName"]]
                stop_obj.naptan_codes.append(stop["naptanId"])
                continue

            stop_obj = Station(
                id=stop["commonName"], #goofy ahh
                name=stop["commonName"],
                lat=stop["lat"],
                lon=stop["lon"],
                naptan_codes=[stop["naptanId"]],
            )
            stops[stop["commonName"]] = stop_obj

        return list(stops.values())
            


    def get_lines_with_routes_and_timetables(self, modes: list[str] = []) -> tuple[list[Line], dict[str, dict]]:
        """
        Get lines with routes AND fetch timetable data for each route
        
        Returns:
            tuple of (lines, timetables_dict)
            where timetables_dict is {line_id: {route_id: timetable_data}}
        """
        self._logger.info("Fetching lines and routes...")
        lines = self.get_lines_with_routes(modes)
        timetables = {}

        self._logger.info(f"Fetching timetables for {len(lines)} lines...")
        
        with tqdm(total=len(lines), desc="Fetching line timetables", unit="line") as line_pbar:
            for line in lines:
                line_pbar.set_description(f"Fetching {line.name}")
                timetables[line.id] = {}
                
                with tqdm(total=len(line.routes), desc=f"  Routes", unit="route", leave=False) as route_pbar:
                    for route in line.routes:
                        route_pbar.set_description(f"  {route.route_id[:30]}")
                        # Get origin stop (first stop in route)
                        if route.route and len(route.route) > 0:
                            origin_naptan = route.route[0].stop_naptan
                            
                            # Fetch timetable for this route origin
                            timetable_data = self.get_timetable_for_route(line.id, [origin_naptan])
                            timetables[line.id][route.route_id] = timetable_data
                            
                            # Update transition times from timetable data
                            self._update_route_times_from_timetable(route, timetable_data)
                        
                        route_pbar.update(1)
                
                line_pbar.update(1)

        return lines, timetables

    def _update_route_times_from_timetable(self, route: Route, timetable_data: dict):
        """Update RouteNode transition_time values from timetable station intervals"""
        if not timetable_data or "stationIntervals" not in timetable_data:
            return
        
        # Build a map of naptan -> time_to_arrival
        time_map = {}
        for interval_group in timetable_data["stationIntervals"]:
            for interval in interval_group.get("intervals", []):
                stop_id = interval.get("stopId")
                time_to_arrival = interval.get("timeToArrival", 0)
                time_map[stop_id] = time_to_arrival
        
        # Update route nodes
        for node in route.route:
            if node.stop_naptan in time_map:
                node.transition_time = time_map[node.stop_naptan]

    def get_all_line_statuses(self, line_ids: list[str] = []) -> list[Delay]:
        GOOD_SERVICE = 10

        if len(line_ids) == 0:
            return []

        URL = f"/Line/{",".join(line_ids)}/Status"
        response = self._make_request("GET", URL, {"detail": "true"})
        delays = []

        for line in response:
            line_id = line.get("id")

            for line_status in line.get("lineStatuses", []):
                if line_status.get("statusSeverity", GOOD_SERVICE) == GOOD_SERVICE:
                    continue
                
                severity_code = line_status.get("statusSeverity")
                status_description = line_status.get("statusSeverityDescription", "")
                disruption = line_status.get("disruption")

                affected_stop_ids = []
                if disruption:
                    for stop in disruption.get("affectedStops", []):
                        stop_id = (
                            stop.get("stationNaptan") or
                            stop.get("hubNaptanCode") or
                            stop.get("naptanId") or
                            stop.get("id")
                        )
                        if stop_id:
                            affected_stop_ids.append(stop_id)

                for validity_period in line_status.get("validityPeriods", []):
                    from_date = validity_period.get("fromDate", "")
                    to_date = validity_period.get("toDate", from_date)

                    delay = Delay(
                        id=f"status-{line_id}-{severity_code}-{from_date}",
                        line_id=line_id,
                        type="lineStatus",
                        category=status_description,
                        categoryDescription=str(severity_code),
                        summary=line_status.get("reason", "No reason provided"),
                        description=line_status.get("reason", ""),
                        additionalInfo="n/a",
                        created=from_date,
                        lastUpdate=to_date,
                        mode="tube",
                        affected_stops=affected_stop_ids
                    )
                    delays.append(delay)
                
        return delays
    
    def get_stations_crowding(self, naptans: list[str]) -> dict[str, dict[str, str]]:
        crowding_data = {}

        for naptan in tqdm(naptans, desc="Fetching station crowding data", unit="station"):
            crowding_data[naptan] = self.get_station_crowding(naptan)

        return crowding_data
    
    def get_station_crowding(self, naptan) -> dict[str, str]:
        URL = f"/crowding/{naptan}/Live"
        response = self._make_request("GET", URL)

        if not response.get("dataAvailable", False):
            return {}
        
        return {
            "crowding": response.get("percentageOfBaseline", 0.0),
            "timestamp": response.get("timeUtc") or datetime.now().isoformat()
        }

    def _make_request(self, method: str, endpoint: str, params: dict[str, str] = {}):
        return request(method, self.base_url + endpoint, params={"app_key": self.app_key} | params).json()