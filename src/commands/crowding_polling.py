"""
Crowding Polling Command

Periodically fetches crowding data from TfL API and stores in database.
Similar to disruption polling, maintains historical crowding patterns.
"""

from sqlalchemy.orm import Session
from data.tfl_client import TflClient
from data.db_models import StationCrowding, Station, Line, StationNaptan
from datetime import datetime, timedelta
from typing import Optional
import logging


class CrowdingPollingCommand:
    """
    Command for polling and storing station crowding data.
    
    Fetches crowding information from TfL API and stores timestamped
    snapshots in the database for route optimization.
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize crowding polling command.
        
        Args:
            db_session: Active database session
        """
        self.db = db_session
        self.client = TflClient()
        self.logger = logging.getLogger(__name__)
    
    def poll_and_update(self) -> dict:
        """
        Fetch current crowding data and update database.
        
        Returns:
            Dictionary with polling statistics:
            {
                'timestamp': str,
                'records_created': int,
                'lines_checked': int,
                'stations_updated': int,
                'errors': list
            }
        """
        timestamp = datetime.now().isoformat()
        self.logger.info(f"Starting crowding data poll at {timestamp}")
        
        stats = {
            'timestamp': timestamp,
            'records_created': 0,
            'lines_checked': 0,
            'stations_updated': set(),
            'errors': []
        }
        
        try:
            lines = self.db.query(Line).all()
            line_ids: list[str] = [str(line.id) for line in lines]
            
            if not line_ids:
                self.logger.warning("No lines found in database")
                return stats
            
            self.logger.info(f"Fetching crowding data for {len(line_ids)} lines")
            crowding_data = self.client.get_line_crowding(line_ids)
            
            stats['lines_checked'] = len(line_ids)
            
            # Process crowding data
            # crowding_data format: {naptan_id: {line_id: [crowding_metrics]}}
            for naptan_id, line_data in crowding_data.items():
                # Find station by NaPTAN code
                station_naptan = self.db.query(StationNaptan).filter(
                    StationNaptan.naptan_code == naptan_id
                ).first()
                
                if not station_naptan:
                    self.logger.debug(f"Station not found for NaPTAN: {naptan_id}")
                    continue
                
                station_id = station_naptan.station_id
                stats['stations_updated'].add(station_id)
                
                # Process each line's crowding data at this station
                for line_id, crowding_metrics in line_data.items():
                    for metric in crowding_metrics:
                        # Create crowding record
                        crowding_record = StationCrowding(
                            station_id=station_id,
                            line_id=line_id,
                            timestamp=timestamp,
                            crowding_level=metric.get('crowding_level'),
                            capacity_percentage=metric.get('capacity_percentage'),
                            time_slice=metric.get('time_slice', 'unknown'),
                            data_source='tfl_api'
                        )
                        
                        self.db.add(crowding_record)
                        stats['records_created'] += 1
            
            # Commit all records
            self.db.commit()
            
            # Clean up old records (keep last 7 days)
            self._cleanup_old_records(days=7)
            
            stats['stations_updated'] = len(stats['stations_updated'])
            self.logger.info(
                f"Crowding poll complete: {stats['records_created']} records created "
                f"for {stats['stations_updated']} stations"
            )
            
        except Exception as e:
            self.logger.error(f"Error during crowding poll: {e}", exc_info=True)
            self.db.rollback()
            stats['errors'].append(str(e))
        
        return stats
    
    def _cleanup_old_records(self, days: int = 7):
        """
        Delete crowding records older than specified days.
        
        Args:
            days: Number of days to retain
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        try:
            deleted = self.db.query(StationCrowding).filter(
                StationCrowding.timestamp < cutoff_date
            ).delete()
            
            self.db.commit()
            
            if deleted > 0:
                self.logger.info(f"Cleaned up {deleted} old crowding records")
                
        except Exception as e:
            self.logger.error(f"Error cleaning up old records: {e}")
            self.db.rollback()
    
    def get_recent_crowding(
        self,
        station_id: Optional[str] = None,
        line_id: Optional[str] = None,
        minutes: int = 30
    ) -> list:
        """
        Retrieve recent crowding data from database.
        
        Args:
            station_id: Filter by station (optional)
            line_id: Filter by line (optional)
            minutes: How many minutes back to query
            
        Returns:
            List of StationCrowding records
        """
        cutoff_time = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        
        query = self.db.query(StationCrowding).filter(
            StationCrowding.timestamp >= cutoff_time
        )
        
        if station_id:
            query = query.filter(StationCrowding.station_id == station_id)
        
        if line_id:
            query = query.filter(StationCrowding.line_id == line_id)
        
        return query.order_by(StationCrowding.timestamp.desc()).all()
    
    def get_crowding_summary(self) -> dict:
        """
        Get summary of most recent crowding data.
        
        Returns:
            Dictionary with crowding statistics:
            {
                'total_stations': int,
                'high_crowding_count': int,
                'average_capacity': float,
                'most_crowded_stations': list
            }
        """
        # Get most recent records (last 30 minutes)
        recent_records = self.get_recent_crowding(minutes=30)
        
        if not recent_records:
            return {
                'total_stations': 0,
                'high_crowding_count': 0,
                'average_capacity': 0.0,
                'most_crowded_stations': []
            }
        
        # Calculate statistics
        station_capacities = {}
        for record in recent_records:
            if record.station_id not in station_capacities:
                station_capacities[record.station_id] = []
            if record.capacity_percentage:
                station_capacities[record.station_id].append(record.capacity_percentage)
        
        # Average capacity per station
        station_averages = {
            station_id: sum(caps) / len(caps)
            for station_id, caps in station_capacities.items()
            if caps
        }
        
        high_crowding_count = sum(
            1 for avg in station_averages.values() if avg > 80
        )
        
        average_capacity = (
            sum(station_averages.values()) / len(station_averages)
            if station_averages else 0.0
        )
        
        # Most crowded stations
        sorted_stations = sorted(
            station_averages.items(),
            key=lambda x: x[1],
            reverse=True
        )
        most_crowded = [
            {'station_id': station_id, 'capacity': capacity}
            for station_id, capacity in sorted_stations[:10]
        ]
        
        return {
            'total_stations': len(station_averages),
            'high_crowding_count': high_crowding_count,
            'average_capacity': round(average_capacity, 2),
            'most_crowded_stations': most_crowded
        }
