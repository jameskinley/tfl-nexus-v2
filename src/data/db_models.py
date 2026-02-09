from pydantic import BaseModel
from typing import Optional

class Mode(BaseModel):
    name: str
    isTflService: bool
    isScheduledService: bool

class Route(BaseModel):
    route_id: str
    name: str
    line: "Line"
    route: list["Station"]

    first_journey_time: Optional[float] = None
    last_journey_time: Optional[float] = None
    interval: Optional[float] = None #minutes between services, if scheduled service.

class Line(BaseModel):
    id: str
    name: str
    mode: Mode
    routes: list[Route]

class Station(BaseModel):
    id: str
    name: str
    naptans: list[str]
    modes: list[Mode]
    lines: list[Line] #transient foreign key to allow for bypass of the route table.
    routes: list[Route]

    previous: Optional["Station"] = None

    time_to_next: Optional[float] = None
    next: Optional["Station"] = None