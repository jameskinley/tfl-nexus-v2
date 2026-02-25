"""
Network Reporting Command

Generates comprehensive network status reports with metrics and summaries.
Stores reports in database for historical analysis.
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from data.db_models import NetworkReport, Disruption, Line, StationCrowding, Station
from data.report_summarizer import ReportSummarizer, SimpleTemplateSummarizer
from data.disruption_analyzer import DisruptionPredictor
from graph.graph_manager import GraphManager
from commands.crowding_operations import CrowdingOperations
from datetime import datetime, timedelta
import json
import logging
from typing import Optional, Dict, Any


class NetworkReportingCommand:
    """
    Command for generating and managing network status reports.
    
    Collects metrics from database, generates summaries, and stores
    reports for historical tracking and analysis.
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize network reporting command.
        
        Args:
            db_session: Active database session
        """
        self.db = db_session
        self.logger = logging.getLogger(__name__)
    
    def generate_report(
        self,
        report_type: str = 'snapshot',
        summarizer: Optional[ReportSummarizer] = None
    ) -> Dict[str, Any]:
        """
        Generate a new network report.
        
        Args:
            report_type: Type of report ('snapshot', 'daily_summary', 'incident')
            summarizer: Optional ReportSummarizer instance (defaults to SimpleTemplateSummarizer)
            
        Returns:
            Dictionary containing the report data and metadata
        """
        now = datetime.now()
        timestamp = now.isoformat()
        self.logger.info(f"Generating {report_type} network report at {timestamp}")
        
        # Use default summarizer if none provided
        if summarizer is None:
            summarizer = SimpleTemplateSummarizer()
        
        try:
            # Collect network metrics
            report_data = {
                'timestamp': timestamp,
                'report_type': report_type,
                'total_disruptions': 0,
                'active_lines_count': 0,
                'affected_lines_count': 0,
                'graph_connectivity_score': 1.0,
                'average_reliability_score': 95.0,
                'graph_metrics': {},
                'line_statuses': {},
                'disruption_breakdown': {},
                'crowding_summary': {}
            }
            
            # 1. Count active disruptions
            active_disruptions = self.db.query(Disruption).filter(
                Disruption.is_active == True
            ).all()
            
            report_data['total_disruptions'] = len(active_disruptions)
            
            # 2. Get line information
            all_lines = self.db.query(Line).all()
            report_data['active_lines_count'] = len(all_lines)
            
            # 3. Disruption breakdown by category
            category_counts = {}
            affected_lines = set()
            disruption_details = []
            
            for disruption in active_disruptions:
                category = disruption.category_description or disruption.category or 'Unknown'
                category_counts[category] = category_counts.get(category, 0) + 1
                affected_lines.add(disruption.line_id)
                
                # Collect disruption details for LLM
                disruption_details.append({
                    'line_id': disruption.line_id,
                    'category': category,
                    'summary': disruption.summary or '',
                    'description': disruption.description or '',
                    'additional_info': disruption.additional_info or ''
                })
            
            report_data['disruption_breakdown'] = category_counts
            report_data['affected_lines_count'] = len(affected_lines)
            report_data['disruption_details'] = disruption_details
            
            # 4. Line statuses
            line_statuses = {}
            for line in all_lines:
                # Find disruptions for this line
                line_disruptions = [
                    d for d in active_disruptions if str(d.line_id) == str(line.id)
                ]
                
                if not line_disruptions:
                    line_statuses[line.name] = 'Good Service'
                else:
                    # Use the worst disruption category
                    worst = self._get_worst_disruption(line_disruptions)
                    line_statuses[line.name] = worst.category_description or worst.category
            
            report_data['line_statuses'] = line_statuses
            
            # 5. Graph connectivity metrics
            try:
                graph_manager = GraphManager()
                graph_manager.build_graph_from_db_with_disruptions(self.db)
                
                import networkx as nx
                graph = graph_manager.graph
                
                report_data['graph_metrics'] = {
                    'nodes': graph.number_of_nodes(),
                    'edges': graph.number_of_edges(),
                    'components': nx.number_connected_components(graph),
                    'density': nx.density(graph)
                }
                
                # Connectivity score (1.0 = fully connected, lower = fragmented)
                components = nx.number_connected_components(graph)
                report_data['graph_connectivity_score'] = 1.0 / components if components > 0 else 0.0
                
            except Exception as e:
                self.logger.warning(f"Failed to calculate graph metrics: {e}")
            
            # 6. Reliability scores
            try:
                predictor = DisruptionPredictor(self.db)
                line_scores = predictor.calculate_line_reliability_scores()
                
                if line_scores:
                    # Convert fragility to reliability percentage
                    reliability_scores = [
                        (1.0 - fragility) * 100
                        for fragility in line_scores.values()
                    ]
                    report_data['average_reliability_score'] = sum(reliability_scores) / len(reliability_scores)
                else:
                    report_data['average_reliability_score'] = 95.0
                    
            except Exception as e:
                self.logger.warning(f"Failed to calculate reliability scores: {e}")
                report_data['average_reliability_score'] = 95.0
            
            # 7. Crowding summary (if available)
            try:
                recent_threshold = datetime.now() - timedelta(minutes=30)
                recent_crowding = self.db.query(StationCrowding).filter(
                    StationCrowding.timestamp >= recent_threshold
                ).all()
                
                if recent_crowding:
                    high_crowding = sum(
                        1 for c in recent_crowding
                        if c.crowding_level in ['high', 'very_high']
                    )
                    
                    report_data['crowding_summary'] = {
                        'total_records': len(recent_crowding),
                        'high_crowding_count': high_crowding,
                        'data_age_minutes': 30
                    }
                    
                    # Get top N most crowded stations with details
                    crowding_ops = CrowdingOperations(self.db)
                    top_crowded = crowding_ops.get_n_most_crowded(10)
                    
                    report_data['top_crowded_stations'] = [
                        {
                            'station_id': c.station_id,
                            'station_name': c.station.name if c.station else 'Unknown',
                            'crowding_level': c.crowding_level,
                            'capacity_percentage': c.capacity_percentage,
                            'timestamp': c.timestamp,
                            'time_slice': c.time_slice
                        }
                        for c in top_crowded
                    ]
            except Exception as e:
                self.logger.warning(f"Failed to get crowding summary: {e}")
            
            # Generate summary text
            summary_text = summarizer.generate_summary(report_data)
            
            # Create database record
            network_report = NetworkReport(
                timestamp=now,
                report_type=report_type,
                report_data=json.dumps(report_data),
                summary_text=summary_text,
                total_disruptions=report_data['total_disruptions'],
                active_lines_count=report_data['active_lines_count'],
                affected_lines_count=report_data['affected_lines_count'],
                graph_connectivity_score=report_data['graph_connectivity_score'],
                average_reliability_score=report_data['average_reliability_score']
            )
            
            self.db.add(network_report)
            self.db.commit()
            
            self.logger.info(f"Network report generated and saved with ID: {network_report.id}")
            
            return {
                'id': network_report.id,
                'timestamp': timestamp,
                'report_type': report_type,
                'summary': summary_text,
                'data': report_data
            }
            
        except Exception as e:
            self.logger.error(f"Error generating network report: {e}", exc_info=True)
            self.db.rollback()
            raise
    
    def get_reports(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        report_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> list:
        """
        Query network reports with filters.
        
        Args:
            start_date: ISO format start date (optional)
            end_date: ISO format end date (optional)
            report_type: Filter by report type (optional)
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of report dictionaries
        """
        query = self.db.query(NetworkReport)
        
        # Apply filters
        # Parse string date filters into datetimes so comparisons use correct DB types
        from dateutil import parser as _parser

        if start_date:
            try:
                sd = _parser.parse(start_date) if isinstance(start_date, str) else start_date
                query = query.filter(NetworkReport.timestamp >= sd)
            except Exception:
                self.logger.warning("Invalid start_date filter: %s", start_date)

        if end_date:
            try:
                ed = _parser.parse(end_date) if isinstance(end_date, str) else end_date
                query = query.filter(NetworkReport.timestamp <= ed)
            except Exception:
                self.logger.warning("Invalid end_date filter: %s", end_date)
        
        if report_type:
            query = query.filter(NetworkReport.report_type == report_type)
        
        # Order by timestamp descending
        query = query.order_by(desc(NetworkReport.timestamp))
        
        # Apply pagination
        reports = query.limit(limit).offset(offset).all()
        
        # Convert to dictionaries
        return [
            {
                'id': r.id,
                'timestamp': r.timestamp,
                'report_type': r.report_type,
                'total_disruptions': r.total_disruptions,
                'active_lines_count': r.active_lines_count,
                'affected_lines_count': r.affected_lines_count,
                'graph_connectivity_score': r.graph_connectivity_score,
                'average_reliability_score': r.average_reliability_score,
                'summary': str(r.summary_text)[:200] + '...' if len(str(r.summary_text)) > 200 else str(r.summary_text)
            }
            for r in reports
        ]
    
    def get_report_by_id(self, report_id: int) -> Optional[Dict[str, Any]]:
        """
        Get single report by ID with full details.
        
        Args:
            report_id: Report ID
            
        Returns:
            Report dictionary or None if not found
        """
        report = self.db.query(NetworkReport).filter(
            NetworkReport.id == report_id
        ).first()
        
        if not report:
            return None
        
        return {
            'id': report.id,
            'timestamp': report.timestamp,
            'report_type': report.report_type,
            'summary': str(report.summary_text),
            'data': json.loads(str(report.report_data)),
            'metadata': {
                'total_disruptions': report.total_disruptions,
                'active_lines_count': report.active_lines_count,
                'affected_lines_count': report.affected_lines_count,
                'graph_connectivity_score': report.graph_connectivity_score,
                'average_reliability_score': report.average_reliability_score
            }
        }
    
    def update_report(
        self,
        report_id: int,
        report_type: Optional[str] = None,
        regenerate_summary: bool = False,
        summarizer: Optional[ReportSummarizer] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing network report.
        
        Args:
            report_id: Report ID to update
            report_type: New report type (optional)
            regenerate_summary: Whether to regenerate metrics and summary
            summarizer: Summarizer to use if regenerating (optional)
            
        Returns:
            Updated report dictionary or None if not found
        """
        report = self.db.query(NetworkReport).filter(
            NetworkReport.id == report_id
        ).first()
        
        if not report:
            return None
        
        # Update report type if provided
        if report_type is not None:
            report.report_type = report_type  # type: ignore
        
        # Regenerate summary if requested
        if regenerate_summary:
            self.logger.info(f"Regenerating summary for report {report_id}")
            
            # Use default summarizer if none provided
            if summarizer is None:
                summarizer = SimpleTemplateSummarizer()
            
            # Parse existing report data
            existing_data = json.loads(str(report.report_data))
            
            # Recalculate all metrics (similar to generate_report)
            timestamp = datetime.now().isoformat()
            report_data = {
                'timestamp': timestamp,
                'report_type': report.report_type,
                'total_disruptions': 0,
                'active_lines_count': 0,
                'affected_lines_count': 0,
                'graph_connectivity_score': 1.0,
                'average_reliability_score': 95.0,
                'graph_metrics': {},
                'line_statuses': {},
                'disruption_breakdown': {},
                'crowding_summary': {}
            }
            
            # Recalculate metrics (same logic as generate_report)
            try:
                # 1. Count active disruptions
                active_disruptions = self.db.query(Disruption).filter(
                    Disruption.is_active == True
                ).all()
                report_data['total_disruptions'] = len(active_disruptions)
                
                # 2. Get line information
                all_lines = self.db.query(Line).all()
                report_data['active_lines_count'] = len(all_lines)
                
                # 3. Disruption breakdown
                category_counts = {}
                affected_lines = set()
                disruption_details = []
                for disruption in active_disruptions:
                    category = disruption.category_description or disruption.category or 'Unknown'
                    category_counts[category] = category_counts.get(category, 0) + 1
                    affected_lines.add(disruption.line_id)
                    
                    # Collect disruption details for LLM
                    disruption_details.append({
                        'line_id': disruption.line_id,
                        'category': category,
                        'summary': disruption.summary or '',
                        'description': disruption.description or '',
                        'additional_info': disruption.additional_info or ''
                    })
                
                report_data['disruption_breakdown'] = category_counts
                report_data['affected_lines_count'] = len(affected_lines)
                report_data['disruption_details'] = disruption_details
                
                # 4. Line statuses
                line_statuses = {}
                for line in all_lines:
                    line_disruptions = [
                        d for d in active_disruptions if str(d.line_id) == str(line.id)
                    ]
                    if not line_disruptions:
                        line_statuses[line.name] = 'Good Service'
                    else:
                        worst = self._get_worst_disruption(line_disruptions)
                        line_statuses[line.name] = worst.category_description or worst.category
                
                report_data['line_statuses'] = line_statuses
                
                # 5. Graph metrics
                try:
                    graph_manager = GraphManager()
                    graph_manager.build_graph_from_db_with_disruptions(self.db)
                    import networkx as nx
                    graph = graph_manager.graph
                    
                    report_data['graph_metrics'] = {
                        'nodes': graph.number_of_nodes(),
                        'edges': graph.number_of_edges(),
                        'components': nx.number_connected_components(graph),
                        'density': nx.density(graph)
                    }
                    
                    components = nx.number_connected_components(graph)
                    report_data['graph_connectivity_score'] = 1.0 / components if components > 0 else 0.0
                except Exception as e:
                    self.logger.warning(f"Failed to calculate graph metrics: {e}")
                
                # 6. Reliability scores
                try:
                    predictor = DisruptionPredictor(self.db)
                    line_scores = predictor.calculate_line_reliability_scores()
                    
                    if line_scores:
                        reliability_scores = [
                            (1.0 - fragility) * 100
                            for fragility in line_scores.values()
                        ]
                        report_data['average_reliability_score'] = sum(reliability_scores) / len(reliability_scores)
                except Exception as e:
                    self.logger.warning(f"Failed to calculate reliability scores: {e}")
                
                # 7. Crowding summary
                try:
                    recent_crowding = self.db.query(StationCrowding).filter(
                        StationCrowding.timestamp >= (datetime.now() - timedelta(minutes=30)).isoformat()
                    ).all()
                    
                    if recent_crowding:
                        high_crowding = sum(
                            1 for c in recent_crowding
                            if c.crowding_level in ['high', 'very_high']
                        )
                        report_data['crowding_summary'] = {
                            'total_records': len(recent_crowding),
                            'high_crowding_count': high_crowding,
                            'data_age_minutes': 30
                        }
                except Exception as e:
                    self.logger.warning(f"Failed to get crowding summary: {e}")
                
                # Generate new summary
                summary_text = summarizer.generate_summary(report_data)
                
                # Update report fields
                report.timestamp = timestamp  # type: ignore
                report.report_data = json.dumps(report_data)  # type: ignore
                report.summary_text = summary_text  # type: ignore
                report.total_disruptions = report_data['total_disruptions']  # type: ignore
                report.active_lines_count = report_data['active_lines_count']  # type: ignore
                report.affected_lines_count = report_data['affected_lines_count']  # type: ignore
                report.graph_connectivity_score = report_data['graph_connectivity_score']  # type: ignore
                report.average_reliability_score = report_data['average_reliability_score']  # type: ignore
                
            except Exception as e:
                self.logger.error(f"Error regenerating report data: {e}", exc_info=True)
                raise
        
        self.db.commit()
        self.logger.info(f"Updated network report {report_id}")
        
        # Return updated report
        return {
            'id': report.id,
            'timestamp': report.timestamp,
            'report_type': report.report_type,
            'summary': str(report.summary_text),
            'data': json.loads(str(report.report_data)),
            'metadata': {
                'total_disruptions': report.total_disruptions,
                'active_lines_count': report.active_lines_count,
                'affected_lines_count': report.affected_lines_count,
                'graph_connectivity_score': report.graph_connectivity_score,
                'average_reliability_score': report.average_reliability_score
            }
        }
    
    def delete_report(self, report_id: int) -> bool:
        """
        Delete a network report.
        
        Args:
            report_id: Report ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        report = self.db.query(NetworkReport).filter(
            NetworkReport.id == report_id
        ).first()
        
        if not report:
            return False
        
        self.db.delete(report)
        self.db.commit()
        
        self.logger.info(f"Deleted network report {report_id}")
        return True
    
    def _get_worst_disruption(self, disruptions: list) -> Any:
        """
        Get the most severe disruption from a list.
        
        Args:
            disruptions: List of Disruption objects
            
        Returns:
            Most severe disruption
        """
        # Priority order (higher = worse)
        severity_order = {
            'closure': 5,
            'suspend': 5,
            'partclosure': 4,
            'partsuspended': 4,
            'severedelays': 3,
            'reducedservice': 2,
            'minordelays': 1,
            'goodservice': 0
        }
        
        worst = disruptions[0]
        worst_severity = 0
        
        for disruption in disruptions:
            category = (disruption.category or '').lower().replace(' ', '')
            severity = severity_order.get(category, 0)
            
            if severity > worst_severity:
                worst = disruption
                worst_severity = severity
        
        return worst
