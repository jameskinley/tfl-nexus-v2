from logging import getLogger
from dotenv import load_dotenv
from . import constants
import os

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
    
    def get_all_line_statuses(self, line_ids: list[str] = []) -> list[Delay]:

        GOOD_SERVICE = 10

        if len(line_ids) == 0:
            return []

        URL = f"/Line/{",".join(line_ids)}/Status"

        response = self._make_request("GET", URL, {"detail": "true"})

        for line in response:
            line_id = line.get("id")

            for line_status in line.get("lineStatuses", []):
                if line_status.get("statusSeverity", GOOD_SERVICE) == GOOD_SERVICE:
                    continue
                
                severity_code = line_status.get("statusSeverity")
                description = line_status.get("statusSeverityDescription", "")

                for validity_period in line_status.get("validityPeriods", []):
                    from_date = validity_period.get("fromDate")
                    to_date = validity_period.get("toDate", "")

                disruption = line_status["disruption"]

                for stop in disruption.get("affectedStops", []):
                    stop_id = stop.get("id")
                    # lookup stop in DB and create disruption for that stop - handle outside of client but just so we are aware
                
        return []

    def get_all_disruptions(self, modes: list[str] = []) -> list[Delay]:
        if len(modes) == 0:
            modes = constants.VALID_MODES

        URL = f"/Line/Mode/{','.join(modes)}/Disruption"

        response = self._make_request("GET", URL)

        self._logger.info(f"Received response from TFL API: {response}")

        disruptions = []

        for disruption in response:
            type = disruption.get("type", "Unknown")
            category = disruption.get("closureText", "Unknown")

            if disruption.get("affectedStops") is [] or disruption.get("affectedRoutes") is []:
                # no affected stops or routes indicates general disruption.
                continue


        
        for disruption in response:
            line_ids = []
            if "affectedRoutes" in disruption and disruption["affectedRoutes"]:
                line_ids = [route.get("lineId") for route in disruption["affectedRoutes"] if route.get("lineId")]
            
            if not line_ids:
                description = disruption.get("description", "")
                summary = disruption.get("summary", "")
                text_to_search = (description + " " + summary).lower()
                
                line_name_map = {
                    "northern": "northern",
                    "central": "central",
                    "piccadilly": "piccadilly",
                    "district": "district",
                    "circle": "circle",
                    "metropolitan": "metropolitan",
                    "hammersmith": "hammersmith-city",
                    "bakerloo": "bakerloo",
                    "jubilee": "jubilee",
                    "victoria": "victoria",
                    "waterloo": "waterloo-city",
                    "elizabeth": "elizabeth",
                    "dlr": "dlr",
                    "overground": "london-overground",
                    "tram": "tram"
                }
                
                for name, line_id in line_name_map.items():
                    if name in text_to_search:
                        line_ids.append(line_id)
                        break
            
            if not line_ids:
                line_ids = ["unknown"]
            
            # Extract affected stops - try multiple fields
            affected_stop_ids = []
            if "affectedStops" in disruption and disruption["affectedStops"]:
                for stop in disruption["affectedStops"]:
                    # Try multiple fields in order of preference
                    stop_id = (
                        stop.get("stationNaptan") or 
                        stop.get("hubNaptanCode") or 
                        stop.get("naptanId") or 
                        stop.get("id")
                    )
                    if stop_id:
                        affected_stop_ids.append(stop_id)
            
            # Also check routeSectionNaptanEntrySequence in affectedRoutes
            if "affectedRoutes" in disruption and disruption["affectedRoutes"]:
                for route in disruption["affectedRoutes"]:
                    if "routeSectionNaptanEntrySequence" in route:
                        for entry in route["routeSectionNaptanEntrySequence"]:
                            if "stopPoint" in entry:
                                stop_point = entry["stopPoint"]
                                stop_id = (
                                    stop_point.get("stationNaptan") or
                                    stop_point.get("hubNaptanCode") or
                                    stop_point.get("naptanId") or
                                    stop_point.get("id")
                                )
                                if stop_id and stop_id not in affected_stop_ids:
                                    affected_stop_ids.append(stop_id)
            
            # Use categoryDescription as primary category (e.g., "Minor Delays")
            # Fall back to category if categoryDescription is empty
            category = disruption.get("categoryDescription", "") or disruption.get("category", "")
            
            for line_id in line_ids:
                delay = Delay(
                    id=f"{category or 'unknown'}-{line_id}-{disruption.get('created', '')}",
                    line_id=line_id,
                    type=disruption.get("type", ""),
                    category=category,
                    categoryDescription=disruption.get("categoryDescription", ""),
                    summary=disruption.get("summary", ""),
                    description=disruption.get("description", ""),
                    additionalInfo=disruption.get("additionalInfo", ""),
                    created=disruption.get("created", ""),
                    lastUpdate=disruption.get("lastUpdate", ""),
                    mode="",
                    affected_stops=affected_stop_ids
                )
                disruptions.append(delay)
        
        return disruptions

    def get_line_crowding(self, line_ids: list[str]) -> dict:
        """
        Fetch crowding data for specified lines
        
        Args:
            line_ids: List of line identifiers to fetch crowding data for
            
        Returns:
            Dictionary mapping station_id -> line_id -> crowding metrics
            Format: {
                station_id: {
                    line_id: {
                        'crowding_level': str,
                        'capacity_percentage': float,
                        'time_slice': str
                    }
                }
            }
        """
        crowding_data = {}
        
        # Fetch line data with crowding information
        URL = f"/Line/{','.join(line_ids)}"
        
        try:
            response = self._make_request("GET", URL)
            
            # Handle single line response (dict) vs multiple lines (list)
            if isinstance(response, dict):
                response = [response]
            
            for line in response:
                line_id = line.get("id")
                
                # Check if crowding data exists
                if "crowding" not in line or not line["crowding"]:
                    continue
                
                crowding = line["crowding"]
                
                # Process trainLoadings (station-level crowding by line)
                if "trainLoadings" in crowding and crowding["trainLoadings"]:
                    for loading in crowding["trainLoadings"]:
                        naptan_to = loading.get("naptanTo")
                        if not naptan_to:
                            continue
                        
                        # Initialize nested dict structure
                        if naptan_to not in crowding_data:
                            crowding_data[naptan_to] = {}
                        
                        if line_id not in crowding_data[naptan_to]:
                            crowding_data[naptan_to][line_id] = []
                        
                        # Categorize crowding level based on value (0-6 scale from TfL)
                        value = loading.get("value", 0)
                        if value <= 1:
                            level = "low"
                        elif value <= 3:
                            level = "moderate"
                        elif value <= 5:
                            level = "high"
                        else:
                            level = "very_high"
                        
                        crowding_data[naptan_to][line_id].append({
                            "crowding_level": level,
                            "capacity_percentage": (value / 6.0) * 100,  # Normalize to percentage
                            "time_slice": loading.get("timeSlice", "unknown"),
                            "direction": loading.get("direction", "unknown")
                        })
                
                # Process passengerFlows (station-level regardless of line)
                if "passengerFlows" in crowding and crowding["passengerFlows"]:
                    # This is aggregate station data, we'll skip for now
                    # as we're focusing on line-specific crowding
                    pass
                    
        except Exception as e:
            self._logger.error(f"Failed to fetch crowding data: {e}")
        
        return crowding_data


    def _make_request(self, method: str, endpoint: str, params: dict[str, str] = {}):
        return request(method, self.base_url + endpoint, params={"app_key": self.app_key} | params).json()