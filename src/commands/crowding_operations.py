from sqlalchemy.orm import Session
from data.db_models import StationCrowding

class CrowdingOperations:
    def __init__(self, db_session: Session):
        self.db_session = db_session

    def get_n_most_crowded(self, n):
        """Get the top N most crowded stations ordered by capacity percentage."""
        return self.db_session.query(StationCrowding)\
        .order_by(StationCrowding.capacity_percentage.desc())\
        .limit(n)\
        .all()
    
    def get_crowding_heatmap(self):
        query_response = self.db_session.query(StationCrowding).all() #join station names, lat and long

        return {
            record.station_id: {
                "crowding_level": record.capacity_percentage,
                "timestamp": record.timestamp,
                "lat": record.station.lat,
                "lon": record.station.lon
            }
            for record in query_response
        }