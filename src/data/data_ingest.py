from .tfl_client import TflClient
from .models import Response, RouteNode, Mode
from logging import getLogger
from .db_models import Station, Mode as DbMode, Line
from uuid import uuid4

class DataIngestCommand:

    def __init__(self):
        self.tfl_client = TflClient()
        self.db_client = None
        self._logger = getLogger(__name__)

    def execute(self):
        lines = self.tfl_client.get_lines_with_routes(modes=["tube"])

        stop_nodes: dict[str, Station] = {}

        #this bit builds the stop graph
        for line in lines:
             for route in line.routes:
                 for idx, stop in enumerate(route.route):
                    if stop_nodes.get(stop.stop_name) is None:
                        stop_nodes[stop.stop_name] = Station(
                            id=uuid4().hex,
                            name=stop.stop_name,
                            naptans=[stop.stop_naptan],
                            modes=[DbMode(
                                name=line.mode.name,
                                isTflService=line.mode.isTflService,
                                isScheduledService=line.mode.isScheduledService)],
                            lines=[Line(
                                id=line.id,
                                name=line.name,
                                mode=DbMode(
                                    name=line.mode.name,
                                    isTflService=line.mode.isTflService,
                                    isScheduledService=line.mode.isScheduledService),
                                routes=[])],
                            routes=[]
                        )
                    else:
                        stop_nodes[stop.stop_name].naptans.append(stop.stop_naptan)
                        stop_nodes[stop.stop_name].modes.append(DbMode(
                            name=line.mode.name,
                            isTflService=line.mode.isTflService,
                            isScheduledService=line.mode.isScheduledService))
                        
                    stop_nodes[stop.stop_name].previous = stop_nodes.get(route.route[idx-1].stop_name) if idx > 0 else None
                    stop_nodes[stop.stop_name].next = stop_nodes.get(route.route[idx+1].stop_name) if idx < len(route.route)-1 else None
                

        # Placeholder for database insertion logic
        # insert Stop models here. Should use some sqlaclhemy trickery to add in the modes as a relationship rather than a json blob, to allow for easier querying later on.

        return Response(status="success", message=f"Ingested {len(routes)} routes from TFL API")