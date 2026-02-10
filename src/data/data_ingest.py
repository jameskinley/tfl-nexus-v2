from logging import getLogger
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session
from tqdm import tqdm

from .database import SessionLocal
from .mapper import ModelMapper
from .models import Response
from .tfl_client import TflClient
from . import constants
from . import db_models as db


class DataIngestCommand:
    """
    Orchestrates the data ingestion pipeline from TfL API to database.
    
    Ingestion phases:
    1. Stops: Fetch all tube stations with geographic data and NaPTAN codes
    2. Lines and Routes: Fetch line definitions and route sequences
    3. Timetables: Fetch schedule data for each route
    4. Commit: Persist all data to database
    """

    def __init__(self):
        self.tfl_client = TflClient()
        self._logger = getLogger(__name__)

    def execute(self, db_session: Optional[Session] = None) -> Response:
        """
        Execute the complete data ingestion pipeline.
        
        Args:
            db_session: Optional database session. If not provided, creates a new one.
            
        Returns:
            Response object with success/error status and message.
        """
        self._logger.info("Starting data ingestion process")

        should_close = False
        if db_session is None:
            db_session = SessionLocal()
            should_close = True

        try:
            mapper = ModelMapper(session=db_session)
            modes = constants.VALID_MODES
            
            stats = self._ingest_stops(db_session, modes)
            stats.update(self._ingest_lines_and_routes(db_session, mapper, modes))
            stats.update(self._ingest_timetables(db_session, mapper, stats["lines"], stats["timetables"]))
            
            message = self._commit_and_report(db_session, stats)
            return Response(status="success", message=message)

        except Exception as e:
            self._logger.error(f"Error during data ingestion: {e}", exc_info=True)
            db_session.rollback()
            return Response(status="error", message=f"Data ingestion failed: {str(e)}")

        finally:
            if should_close:
                db_session.close()

    def _ingest_stops(self, db_session: Session, modes: list[str] | None = None) -> dict:
        """
        Fetch and ingest all stop points with geographic data from TfL API.
        
        Creates Station records with lat/lon coordinates and associated NaPTAN codes.
        Returns statistics about ingested stops.
        """
        if modes is None:
            modes = constants.VALID_MODES
        
        self._logger.info(f"Fetching stops for modes: {modes}")
        api_stations = self.tfl_client.get_stop_points_by_mode(modes=modes)
        
        self._logger.info(f"Processing {len(api_stations)} stations")
        
        ingested_count = 0
        with tqdm(total=len(api_stations), desc="Ingesting stops", unit="stop") as pbar:
            for api_station in api_stations:
                db_station = db.Station(
                    id=uuid4().hex,
                    name=api_station.name,
                    lat=api_station.lat,
                    lon=api_station.lon
                )
                
                for naptan_code in api_station.naptan_codes:
                    db_station.naptans.append(db.StationNaptan(naptan_code=naptan_code))
                
                db_session.add(db_station)
                ingested_count += 1
                pbar.update(1)
        
        db_session.flush()
        self._logger.info(f"Ingested {ingested_count} stations with geographic data")
        
        return {"stations": ingested_count}

    def _ingest_lines_and_routes(
        self, 
        db_session: Session, 
        mapper: ModelMapper, 
        modes: list[str]
    ) -> dict:
        """
        Fetch and ingest line definitions and route sequences from TfL API.
        
        Returns lines data and timetable mapping for subsequent processing.
        """
        self._logger.info(f"Fetching lines and routes for modes: {modes}")
        lines, timetables = self.tfl_client.get_lines_with_routes_and_timetables(modes=modes)
        
        self._logger.info(f"Processing {len(lines)} lines")
        
        total_routes = 0
        with tqdm(total=len(lines), desc="Processing lines", unit="line") as pbar:
            for api_line in lines:
                pbar.set_description(f"Processing {api_line.name}")
                
                db_line = mapper.api_line_to_db(api_line, include_routes=True)
                db_session.add(db_line)
                
                total_routes += len(db_line.routes)
                pbar.update(1)
        
        self._logger.info(f"Processed {len(lines)} lines with {total_routes} routes")
        
        return {
            "lines": lines,
            "timetables": timetables,
            "line_count": len(lines),
            "route_count": total_routes
        }

    def _ingest_timetables(
        self,
        db_session: Session,
        mapper: ModelMapper,
        lines: list,
        timetables: dict
    ) -> dict:
        """
        Add timetable data to routes.
        
        Args:
            db_session: Database session
            mapper: Model mapper instance
            lines: List of API line objects
            timetables: Dictionary mapping line_id -> route_id -> timetable_data
            
        Returns:
            Statistics about timetables processed.
        """
        self._logger.info("Adding timetable data to routes")
        
        timetable_count = 0
        for api_line in lines:
            if api_line.id not in timetables:
                continue
                
            db_line = db_session.query(db.Line).filter_by(id=api_line.id).first()
            if not db_line:
                self._logger.warning(f"Line {api_line.id} not found in database")
                continue
            
            for db_route in db_line.routes:
                if db_route.route_id in timetables[api_line.id]:
                    timetable_data = timetables[api_line.id][db_route.route_id]
                    mapper.add_timetable_to_route(db_route, timetable_data)
                    timetable_count += 1
        
        self._logger.info(f"Added timetable data to {timetable_count} routes")
        
        return {"timetable_count": timetable_count}

    def _commit_and_report(self, db_session: Session, stats: dict) -> str:
        """
        Commit all changes to database and generate summary report.
        
        Args:
            db_session: Database session to commit
            stats: Statistics collected during ingestion
            
        Returns:
            Summary message with ingestion statistics.
        """
        self._logger.info("Committing data to database")
        db_session.commit()
        
        message = (
            f"Successfully ingested {stats.get('stations', 0)} stations, "
            f"{stats.get('line_count', 0)} lines, "
            f"{stats.get('route_count', 0)} routes, "
            f"and {stats.get('timetable_count', 0)} timetables"
        )
        self._logger.info(message)
        
        return message