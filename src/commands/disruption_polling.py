from sqlalchemy.orm import Session
from data.tfl_client import TflClient
from data import db_models
import logging
from datetime import datetime


class DisruptionPollingCommand:
    def __init__(self):
        self.tfl_client = TflClient()
        self.logger = logging.getLogger(__name__)

    def poll_and_store_disruptions(self, db_session: Session) -> dict:
        """
        Poll TfL API for disruptions and store them in the database.
        Updates existing disruptions and marks resolved ones as inactive.
        
        Returns:
            dict: Summary of polling results
        """
        try:
            self.logger.info("Polling TfL API for disruptions...")
            
            delay_models = self.tfl_client.get_all_disruptions()
            
            disruption_ids_seen = set()
            new_count = 0
            updated_count = 0
            
            for delay in delay_models:
                disruption_ids_seen.add(delay.id)
                
                existing = db_session.query(db_models.Disruption).filter(
                    db_models.Disruption.id == delay.id
                ).first()
                
                if existing:
                    existing.last_update = delay.lastUpdate
                    existing.summary = delay.summary
                    existing.description = delay.description
                    existing.additional_info = delay.additionalInfo
                    existing.category = delay.category
                    existing.category_description = delay.categoryDescription
                    existing.is_active = True
                    
                    db_session.query(db_models.DisruptedStop).filter(
                        db_models.DisruptedStop.disruption_id == delay.id
                    ).delete()
                    
                    for stop_id in delay.affected_stops:
                        station = db_session.query(db_models.Station).filter(
                            db_models.Station.id == stop_id
                        ).first()
                        
                        if not station:
                            naptan_match = db_session.query(db_models.Station).join(
                                db_models.StationNaptan
                            ).filter(
                                db_models.StationNaptan.naptan_code == stop_id
                            ).first()
                            
                            if naptan_match:
                                station = naptan_match
                        
                        if station:
                            disrupted_stop = db_models.DisruptedStop(
                                disruption_id=delay.id,
                                station_id=station.id
                            )
                            db_session.add(disrupted_stop)
                    
                    updated_count += 1
                else:
                    new_disruption = db_models.Disruption(
                        id=delay.id,
                        line_id=delay.line_id,
                        type=delay.type,
                        category=delay.category,
                        category_description=delay.categoryDescription,
                        summary=delay.summary,
                        description=delay.description,
                        additional_info=delay.additionalInfo,
                        created=delay.created,
                        last_update=delay.lastUpdate,
                        is_active=True
                    )
                    db_session.add(new_disruption)
                    db_session.flush()
                    
                    for stop_id in delay.affected_stops:
                        station = db_session.query(db_models.Station).filter(
                            db_models.Station.id == stop_id
                        ).first()
                        
                        if not station:
                            naptan_match = db_session.query(db_models.Station).join(
                                db_models.StationNaptan
                            ).filter(
                                db_models.StationNaptan.naptan_code == stop_id
                            ).first()
                            
                            if naptan_match:
                                station = naptan_match
                        
                        if station:
                            disrupted_stop = db_models.DisruptedStop(
                                disruption_id=delay.id,
                                station_id=station.id
                            )
                            db_session.add(disrupted_stop)
                    
                    new_count += 1
            
            active_disruptions = db_session.query(db_models.Disruption).filter(
                db_models.Disruption.is_active == True
            ).all()
            
            resolved_count = 0
            for disruption in active_disruptions:
                if disruption.id not in disruption_ids_seen:
                    disruption.is_active = False
                    resolved_count += 1
            
            db_session.commit()
            
            result = {
                "timestamp": datetime.now().isoformat(),
                "new": new_count,
                "updated": updated_count,
                "resolved": resolved_count,
                "total_active": len(disruption_ids_seen)
            }
            
            self.logger.info(f"Disruption poll complete: {result}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error polling disruptions: {e}", exc_info=True)
            db_session.rollback()
            raise
