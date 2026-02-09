from pydantic import BaseModel
from typing import Optional

class Response(BaseModel):
    status: str
    message: str

class RouteNode(BaseModel):
    ordinal: int
    stop_name: str
    line: str
    mode: str
    distance: float
    stop_naptan: str
    transition_time: float

class Route(BaseModel):
    route_id: str
    route: list[RouteNode]
    robustness_score: float = 0
    modes_used: list[str] = []
    total_time: float = 0
    total_distance: float = 0

class RouteResponse(Response):
    route_candidates: list[Route]

class Delay(BaseModel):
    id: str
    line_id: str
    mode: Optional[str] #usually can be inferred from line!
    type: str

    category: str
    categoryDescription: str

    description: str
    summary: str
    additionalInfo: str
    created: str
    lastUpdate: str
    
    # When there are only delays / suspensions between A and B!
    from_stop: Optional[str] = None
    to_stop: Optional[str] = None

class Mode(BaseModel):
    name: str
    isTflService: bool
    isScheduledService: bool

class GetModesResponse(Response):
    modes: list[Mode]

class Line(BaseModel):
    id: str
    name: str
    mode: Mode
    disruptions: list[Delay]
    routes: list[Route] = []