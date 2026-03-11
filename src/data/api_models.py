from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List, Generic, TypeVar
from datetime import datetime

T = TypeVar('T')

class Link(BaseModel):
    href: str
    method: str = "GET"
    rel: Optional[str] = None

class Links(BaseModel):
    self: Link
    model_config = ConfigDict(extra='allow')

class PaginationMeta(BaseModel):
    total: int
    count: int
    page: int = 1
    per_page: int = 50
    total_pages: int

class ResourceResponse(BaseModel, Generic[T]):
    data: T
    links: Links

class CollectionResponse(BaseModel, Generic[T]):
    data: List[T]
    meta: PaginationMeta
    links: Links

class ErrorDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str

class StationData(BaseModel):
    id: str
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    modes: List[str] = Field(default_factory=list)

class LineData(BaseModel):
    id: str
    name: str
    mode: str

class RouteSegment(BaseModel):
    station: StationData
    line: Optional[str] = None
    arrival_time: Optional[str] = None
    departure_time: Optional[str] = None
    wait_time_minutes: float = 0.0

class JourneyRoute(BaseModel):
    total_time_minutes: float
    total_stops: int
    changes: int
    segments: List[RouteSegment]
    has_disruptions: bool = False
    disruption_warnings: List[str] = Field(default_factory=list)

class JourneyData(BaseModel):
    origin: StationData
    destination: StationData
    requested_time: str
    strategy: str
    primary_route: JourneyRoute
    alternatives: List[JourneyRoute] = Field(default_factory=list)

class DisruptionData(BaseModel):
    id: str
    line_id: str
    type: str
    category: str
    category_description: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    additional_info: Optional[str] = None
    created: Optional[str] = None
    last_update: Optional[str] = None
    is_active: bool = True
    affected_stops_count: int = 0

class NetworkTopologyData(BaseModel):
    nodes: int
    edges: int
    average_degree: float
    connected_components: int
    network_health: str

class DataImportJobData(BaseModel):
    id: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    progress_message: Optional[str] = None

class SystemStatisticsData(BaseModel):
    lines: int
    routes: int
    stations: int
    schedules: int
    disruptions: int
    last_updated: Optional[str] = None

class ModeData(BaseModel):
    id: str
    name: str
    is_tfl_service: bool
    is_scheduled_service: bool

class RoutingStrategyData(BaseModel):
    name: str
    description: str
    priority: str

class CrowdingData(BaseModel):
    station_id: str
    line_id: Optional[str] = None
    crowding_level: Optional[str] = None
    capacity_percentage: Optional[float] = None
    timestamp: str
    lat: Optional[float] = None
    lon: Optional[float] = None

class ReportData(BaseModel):
    id: int
    timestamp: str
    report_type: str
    summary: str
    total_disruptions: int
    active_lines_count: int
    affected_lines_count: int
    graph_connectivity_score: Optional[float] = None
    average_reliability_score: Optional[float] = None

class CreateReportRequest(BaseModel):
    report_type: str = Field(default="snapshot", pattern="^(snapshot|daily_summary|incident)$")

class UpdateReportRequest(BaseModel):
    report_type: Optional[str] = Field(default=None, pattern="^(snapshot|daily_summary|incident)$")
    regenerate_summary: bool = False

class CreateDataImportRequest(BaseModel):
    full_refresh: bool = False
