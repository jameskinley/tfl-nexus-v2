from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Table, Text, DateTime
from sqlalchemy.orm import relationship, declarative_base
from typing import Optional

Base = declarative_base()

# Association tables for many-to-many relationships
station_mode_association = Table(
    'station_mode',
    Base.metadata,
    Column('station_id', String, ForeignKey('stations.id'), primary_key=True),
    Column('mode_name', String, ForeignKey('modes.name'), primary_key=True)
)

station_line_association = Table(
    'station_line',
    Base.metadata,
    Column('station_id', String, ForeignKey('stations.id'), primary_key=True),
    Column('line_id', String, ForeignKey('lines.id'), primary_key=True)
)


class Mode(Base):
    __tablename__ = 'modes'

    name = Column(String, primary_key=True)
    isTflService = Column(Boolean, nullable=False)
    isScheduledService = Column(Boolean, nullable=False)

    # Relationships
    lines = relationship("Line", back_populates="mode")
    stations = relationship("Station", secondary=station_mode_association, back_populates="modes")


class Line(Base):
    __tablename__ = 'lines'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    mode_name = Column(String, ForeignKey('modes.name'), nullable=False)

    # Relationships
    mode = relationship("Mode", back_populates="lines")
    routes = relationship("Route", back_populates="line", cascade="all, delete-orphan")
    stations = relationship("Station", secondary=station_line_association, back_populates="lines")


class Route(Base):
    __tablename__ = 'routes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    line_id = Column(String, ForeignKey('lines.id'), nullable=False)

    # Relationships
    line = relationship("Line", back_populates="routes")
    station_intervals = relationship("StationInterval", back_populates="route", 
                                    cascade="all, delete-orphan", order_by="StationInterval.ordinal")
    schedules = relationship("Schedule", back_populates="route", cascade="all, delete-orphan")


class Station(Base):
    __tablename__ = 'stations'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True, index=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)

    modes = relationship("Mode", secondary=station_mode_association, back_populates="stations")
    lines = relationship("Line", secondary=station_line_association, back_populates="stations")
    naptans = relationship("StationNaptan", back_populates="station", cascade="all, delete-orphan")
    intervals = relationship("StationInterval", back_populates="station")


class StationNaptan(Base):
    """Stores NaPTAN codes for each station (one-to-many)"""
    __tablename__ = 'station_naptans'

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(String, ForeignKey('stations.id'), nullable=False)
    naptan_code = Column(String, nullable=False, index=True)

    # Relationships
    station = relationship("Station", back_populates="naptans")


class StationInterval(Base):
    """Represents a stop in a route sequence with timing information"""
    __tablename__ = 'station_intervals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(Integer, ForeignKey('routes.id'), nullable=False)
    station_id = Column(String, ForeignKey('stations.id'), nullable=False)
    ordinal = Column(Integer, nullable=False)  # Position in route sequence
    time_to_arrival = Column(Float, nullable=True)  # Minutes from route origin

    # Relationships
    route = relationship("Route", back_populates="station_intervals")
    station = relationship("Station", back_populates="intervals")


class Schedule(Base):
    """Service schedules for a route (e.g., weekday, weekend)"""
    __tablename__ = 'schedules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(Integer, ForeignKey('routes.id'), nullable=False)
    name = Column(String, nullable=False)  # e.g., "Monday - Thursday", "Saturday"
    
    # First and last journey times (in minutes from midnight)
    first_journey_time = Column(Float, nullable=True)
    last_journey_time = Column(Float, nullable=True)

    # Relationships
    route = relationship("Route", back_populates="schedules")
    periods = relationship("Period", back_populates="schedule", cascade="all, delete-orphan")
    known_journeys = relationship("KnownJourney", back_populates="schedule", cascade="all, delete-orphan")


class Period(Base):
    """Service frequency periods within a schedule"""
    __tablename__ = 'periods'

    id = Column(Integer, primary_key=True, autoincrement=True)
    schedule_id = Column(Integer, ForeignKey('schedules.id'), nullable=False)
    
    period_type = Column(String, nullable=False)  # e.g., "Normal", "FrequencyHours"
    from_time = Column(Float, nullable=False)  # Minutes from midnight
    to_time = Column(Float, nullable=False)  # Minutes from midnight
    frequency_min = Column(Float, nullable=True)  # Highest frequency (minutes between services)
    frequency_max = Column(Float, nullable=True)  # Lowest frequency (minutes between services)

    # Relationships
    schedule = relationship("Schedule", back_populates="periods")


class KnownJourney(Base):
    """Specific scheduled departure times"""
    __tablename__ = 'known_journeys'

    id = Column(Integer, primary_key=True, autoincrement=True)
    schedule_id = Column(Integer, ForeignKey('schedules.id'), nullable=False)
    
    departure_time = Column(Float, nullable=False)
    interval_id = Column(Integer, nullable=True)

    schedule = relationship("Schedule", back_populates="known_journeys")


class Disruption(Base):
    """Stores current and historical disruptions"""
    __tablename__ = 'disruptions'

    id = Column(String, primary_key=True)
    line_id = Column(String, ForeignKey('lines.id'), nullable=False)
    type = Column(String, nullable=False)
    category = Column(String, nullable=False)
    category_description = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    additional_info = Column(Text, nullable=True)
    created = Column(String, nullable=True)
    last_update = Column(String, nullable=True)
    closure_text = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # ML and analytics fields
    resolved_at = Column(String, nullable=True)  # When disruption ended
    duration_minutes = Column(Float, nullable=True)  # Calculated duration
    disruption_probability_score = Column(Float, nullable=True)  # ML-based reliability score
    
    line = relationship("Line", foreign_keys=[line_id])
    affected_stops = relationship("DisruptedStop", back_populates="disruption", cascade="all, delete-orphan")
    events = relationship("DisruptionEvent", back_populates="disruption", cascade="all, delete-orphan")


class DisruptedStop(Base):
    """Stores stops affected by disruptions"""
    __tablename__ = 'disrupted_stops'

    id = Column(Integer, primary_key=True, autoincrement=True)
    disruption_id = Column(String, ForeignKey('disruptions.id'), nullable=False)
    station_id = Column(String, ForeignKey('stations.id'), nullable=False)
    
    disruption = relationship("Disruption", back_populates="affected_stops")
    station = relationship("Station")


class DisruptionEvent(Base):
    """Tracks disruption lifecycle events for ML training"""
    __tablename__ = 'disruption_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    disruption_id = Column(String, ForeignKey('disruptions.id'), nullable=False)
    event_type = Column(String, nullable=False)  # 'created', 'updated', 'escalated', 'resolved'
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Event context for ML features
    previous_category = Column(String, nullable=True)
    new_category = Column(String, nullable=True)
    affected_stations_count = Column(Integer, default=0)
    time_of_day = Column(String, nullable=True)  # 'peak', 'off-peak', 'night'
    day_of_week = Column(String, nullable=True)
    concurrent_disruptions = Column(Integer, default=0)
    
    # Relationships
    disruption = relationship("Disruption", back_populates="events")


class StationCrowding(Base):
    """Stores historical crowding data for stations"""
    __tablename__ = 'station_crowding'

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(String, ForeignKey('stations.id'), nullable=False, index=True)
    line_id = Column(String, ForeignKey('lines.id'), nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Crowding metrics
    crowding_level = Column(String, nullable=True)  # 'low', 'moderate', 'high', 'very_high'
    capacity_percentage = Column(Float, nullable=True)  # 0-100+
    time_slice = Column(String, nullable=True)  # Time period from TfL API
    data_source = Column(String, default='tfl_api')  # 'tfl_api', 'manual', 'predicted'
    
    # Relationships
    station = relationship("Station")
    line = relationship("Line")


class NetworkReport(Base):
    """Stores network state snapshots and analyses"""
    __tablename__ = 'network_reports'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    report_type = Column(String, nullable=False)  # 'snapshot', 'daily_summary', 'incident'
    
    # Report data (JSON stored as text)
    report_data = Column(Text, nullable=False)  # JSON with full metrics
    summary_text = Column(Text, nullable=False)  # Human-readable summary
    
    # Quick-access metadata (duplicated from JSON for querying)
    total_disruptions = Column(Integer, default=0)
    active_lines_count = Column(Integer, default=0)
    affected_lines_count = Column(Integer, default=0)
    graph_connectivity_score = Column(Float, nullable=True)
    average_reliability_score = Column(Float, nullable=True)


class PollingMeta(Base):
    """Tracks polling metadata to prevent excessive API calls"""
    __tablename__ = 'polling_meta'

    id = Column(Integer, primary_key=True, autoincrement=True)
    poll_type = Column(String, unique=True, nullable=False, index=True)
    last_poll_timestamp = Column(DateTime, nullable=False)
    poll_interval_seconds = Column(Integer, nullable=False)