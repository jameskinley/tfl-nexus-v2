from requests import request
from .models import *
from logging import getLogger
from .naptan_lookup import NaPTANLookup

class TflClient:
    def __init__(self):
        self.base_url = "https://api.tfl.gov.uk"
        self.app_id = None
        self.app_key = None
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
    
    def build_timetable(self, line_id: str, origin_stop: str):
        URL = f"/Line/{line_id}/Timetable/{origin_stop}"
        response = self._make_request("GET", URL)

        # Placeholder for timetable parsing logic
        return response

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
        return request(method, self.base_url + endpoint).json()