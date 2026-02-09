from requests import request
from .models import *
from logging import getLogger
from .naptan_lookup import NaPTANLookup
from tqdm import tqdm
from dotenv import load_dotenv
import os

load_dotenv()

class TflClient:
    def __init__(self):
        self.base_url = "https://api.tfl.gov.uk"
        self.app_key = os.getenv("TFL_PRIMARY_KEY")
        self._logger = getLogger(__name__)
        self.naptan_lookup = NaPTANLookup()

    def get_valid_disruption_categories(self) -> list[str]:
        URL = "/Line/Meta/DisruptionCategories"

        response = self._make_request("GET", URL)

        self._logger.info(f"Received response from TFL API: {response}")

        return response

    def get_valid_modes(self) -> list[Mode]:
        URL = "/Line/Meta/Modes"

        response = self._make_request("GET", URL)

        self._logger.info(f"Received response from TFL API: {response}")

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
                        stop_name=self.naptan_lookup.get_stop_name(stop),
                        stop_naptan=stop,
                        line=line_id,
                        mode=lines[line_id].mode.name,
                        distance=0,
                        transition_time=0
                    ) for idx, stop in enumerate(route["naptanIds"])]
                ))

        return list(lines.values())

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

    def get_lines_with_disruptions(self, modes: list[str] = []) -> list[Line]:

        mode_collection = self.get_valid_modes() 
        
        if len(modes) == 0:
            modes = [mode.name for mode in mode_collection if mode.isTflService]

        URL = f"/Line/Mode/{",".join(modes)}/Route"
        self._logger.info(f"Making request to TFL API with URL: {URL}")

        response = self._make_request("GET", URL)

        mode_list = {mode.name: mode for mode in mode_collection}

        lines = dict[str, Line]()

        self._logger.info(f"Received response from TFL API: {response}")

        for res in response:
            line = Line(
                id=res["id"],
                name=res["name"],
                mode=mode_list[res["modeName"]],    
                disruptions=self._parse_disruptions(res)
            )
            lines[line.id] = line

        return list(lines.values())
    
    def _parse_disruptions(self, line_response) -> list[Delay]:
        disruptions = []

        for disruption in line_response["disruptions"]:
            disruption_model = Delay(
                id = disruption["id"] if "id" in disruption else "no-id",
                line_id=line_response["lineId"],
                type=disruption["type"],
                category=disruption["category"],
                categoryDescription=disruption["categoryDescription"],
                summary=disruption["summary"],
                description=disruption["description"],
                additionalInfo=disruption["additionalInfo"],
                created=disruption["created"],
                lastUpdate=disruption["lastUpdate"],
                mode="here to stop error x"
            )
            disruptions.append(disruption_model)

        return disruptions

    def _make_request(self, method: str, endpoint: str):
        return request(method, self.base_url + endpoint, params={"app_key": self.app_key}).json()