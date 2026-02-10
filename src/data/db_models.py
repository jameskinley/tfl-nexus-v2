from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Table, Text
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
    
    departure_time = Column(Float, nullable=False)  # Minutes from midnight
    interval_id = Column(Integer, nullable=True)  # Reference to which station interval set applies

    # Relationships
    schedule = relationship("Schedule", back_populates="known_journeys")