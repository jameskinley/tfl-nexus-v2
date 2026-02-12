from sqlalchemy.orm import Session
from data import db_models


class StatsOperationsCommand:
    def __init__(self, db_session: Session):
        self.db_session = db_session

    def get_database_stats(self) -> dict:
        line_count = self.db_session.query(db_models.Line).count()
        route_count = self.db_session.query(db_models.Route).count()
        station_count = self.db_session.query(db_models.Station).count()
        schedule_count = self.db_session.query(db_models.Schedule).count()
        
        return {
            "lines": line_count,
            "routes": route_count,
            "stations": station_count,
            "schedules": schedule_count
        }
