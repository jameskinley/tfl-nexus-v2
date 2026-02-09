from .tfl_client import TflClient
from .models import Response
from .database import get_db_session
from .mapper import ModelMapper
from logging import getLogger
from sqlalchemy.orm import Session
from typing import Optional
from tqdm import tqdm

class DataIngestCommand:

    def __init__(self):
        self.tfl_client = TflClient()
        self._logger = getLogger(__name__)

    def execute(self, db_session: Optional[Session] = None) -> Response:
        """
        Execute the data ingestion process:
        1. Fetch lines and routes from TfL API
        2. Fetch timetable data for each route
        3. Convert API models to DB models using mapper
        4. Store everything in the database
        """
        self._logger.info("Starting data ingestion process...")

        # Use provided session or create a new one
        should_close = False
        if db_session is None:
            from .database import SessionLocal
            db_session = SessionLocal()
            should_close = True

        try:
            # Initialize mapper with session
            mapper = ModelMapper(session=db_session)

            # Fetch lines with routes and timetables
            self._logger.info("Fetching lines, routes, and timetables from TfL API...")
            lines, timetables = self.tfl_client.get_lines_with_routes_and_timetables(modes=["tube"])
            
            self._logger.info(f"Fetched {len(lines)} lines with timetables")

            # Process each line with progress bar
            total_routes = 0
            total_stations = 0
            
            with tqdm(total=len(lines), desc="Processing lines", unit="line") as pbar:
                for api_line in lines:
                    pbar.set_description(f"Processing {api_line.name}")
                    self._logger.info(f"Processing line: {api_line.name} ({api_line.id})")
                    
                    # Convert API line to DB line (with routes)
                    db_line = mapper.api_line_to_db(api_line, include_routes=True)
                    
                    # Add timetable data to each route
                    if api_line.id in timetables:
                        route_pbar = tqdm(total=len(db_line.routes), desc=f"  Routes for {api_line.name}", 
                                         unit="route", leave=False)
                        for db_route in db_line.routes:
                            if db_route.route_id in timetables[api_line.id]:
                                timetable_data = timetables[api_line.id][db_route.route_id]
                                mapper.add_timetable_to_route(db_route, timetable_data)
                                self._logger.info(
                                    f"  Added timetable data to route: {db_route.route_id} "
                                    f"({len(timetable_data.get('schedules', []))} schedules)"
                                )
                            route_pbar.update(1)
                        route_pbar.close()
                    
                    # Add line to session
                    db_session.add(db_line)
                    total_routes += len(db_line.routes)
                    
                    # Count unique stations from mapper cache
                    total_stations = len(mapper._station_cache)
                    
                    pbar.update(1)

            # Commit all changes
            self._logger.info("Committing data to database...")
            db_session.commit()
            
            message = (
                f"Successfully ingested {len(lines)} lines, "
                f"{total_routes} routes, and {total_stations} stations"
            )
            self._logger.info(message)
            
            return Response(status="success", message=message)

        except Exception as e:
            self._logger.error(f"Error during data ingestion: {e}", exc_info=True)
            db_session.rollback()
            return Response(status="error", message=f"Data ingestion failed: {str(e)}")

        finally:
            if should_close:
                db_session.close()