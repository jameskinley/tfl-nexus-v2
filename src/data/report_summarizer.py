"""
Report Summarizer Interface

Provides pluggable text summarization for network reports.
Supports template-based and LLM-based summary generation.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
import logging
from llm.openrouter_client import OpenRouterClient
import json

class ReportSummarizer(ABC):
    """
    Abstract base class for report summarizers.
    
    Defines interface for generating human-readable summaries
    from structured report data.
    """
    
    def __init__(self, name: str):
        """
        Initialize summarizer.
        
        Args:
            name: Human-readable name for this summarizer
        """
        self.name = name
        self.logger = logging.getLogger(__name__)
    
    @abstractmethod
    def generate_summary(self, report_data: Dict[str, Any]) -> str:
        """
        Generate text summary from report data.
        
        Args:
            report_data: Dictionary containing report metrics:
                - 'timestamp': ISO format timestamp
                - 'report_type': Type of report
                - 'total_disruptions': Count of active disruptions
                - 'active_lines_count': Total lines in network
                - 'affected_lines_count': Lines with disruptions
                - 'graph_metrics': Dict with connectivity stats
                - 'line_statuses': Dict mapping line_id -> status
                - 'disruption_breakdown': Dict of disruptions by category
                - 'average_reliability_score': Float 0-100
                
        Returns:
            Human-readable text summary
        """
        pass


class SimpleTemplateSummarizer(ReportSummarizer):
    """
    Template-based summarizer using string formatting.
    
    Generates concise, structured summaries suitable for alerts and dashboards.
    Fast and deterministic with no external dependencies.
    """
    
    def __init__(self):
        super().__init__("Simple Template")
    
    def generate_summary(self, report_data: Dict[str, Any]) -> str:
        """
        Generate template-based summary.
        
        Creates multi-paragraph summary with:
        - Overall network status
        - Disruption details
        - Connectivity and reliability metrics
        """
        # Extract key metrics
        timestamp = report_data.get('timestamp', 'Unknown time')
        report_type = report_data.get('report_type', 'snapshot')
        total_disruptions = report_data.get('total_disruptions', 0)
        active_lines = report_data.get('active_lines_count', 0)
        affected_lines = report_data.get('affected_lines_count', 0)
        reliability = report_data.get('average_reliability_score', 0.0)
        
        # Build summary sections
        sections = []
        
        # Header with timestamp
        header = f"Network Report - {self._format_timestamp(timestamp)}"
        sections.append(header)
        sections.append("=" * len(header))
        sections.append("")
        
        # Overall status
        if total_disruptions == 0:
            status = f"✓ Network Status: Good Service on all {active_lines} lines"
        else:
            status = (
                f"⚠ Network Status: {total_disruptions} active disruption(s) "
                f"affecting {affected_lines} of {active_lines} lines"
            )
        sections.append(status)
        sections.append("")
        
        # Disruption details
        if total_disruptions > 0:
            disruption_breakdown = report_data.get('disruption_breakdown', {})
            if disruption_breakdown:
                sections.append("Disruption Breakdown:")
                for category, count in sorted(disruption_breakdown.items()):
                    sections.append(f"  • {category}: {count}")
                sections.append("")
            
            # Affected lines
            line_statuses = report_data.get('line_statuses', {})
            if line_statuses:
                affected = [
                    (line_id, status)
                    for line_id, status in line_statuses.items()
                    if status != 'Good Service'
                ]
                if affected:
                    sections.append("Affected Lines:")
                    for line_id, status in sorted(affected)[:10]:  # Top 10
                        sections.append(f"  • {line_id}: {status}")
                    sections.append("")
        
        # Network metrics
        graph_metrics = report_data.get('graph_metrics', {})
        if graph_metrics:
            sections.append("Network Metrics:")
            sections.append(f"  • Total Stations: {graph_metrics.get('nodes', 0)}")
            sections.append(f"  • Total Connections: {graph_metrics.get('edges', 0)}")
            sections.append(f"  • Network Components: {graph_metrics.get('components', 1)}")
            
            if graph_metrics.get('components', 1) > 1:
                sections.append("  ⚠ Warning: Network fragmentation detected")
            sections.append("")
        
        # Reliability score
        reliability_status = self._get_reliability_status(reliability)
        sections.append(f"Overall Reliability: {reliability:.1f}% ({reliability_status})")
        sections.append("")
        
        # Footer
        sections.append(f"Report Type: {report_type.title()}")
        
        return "\n".join(sections)
    
    def _format_timestamp(self, iso_timestamp: str) -> str:
        """Format ISO timestamp to readable string."""
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return iso_timestamp
    
    def _get_reliability_status(self, score: float) -> str:
        """Convert reliability score to status label."""
        if score >= 95:
            return "Excellent"
        elif score >= 85:
            return "Good"
        elif score >= 70:
            return "Fair"
        elif score >= 50:
            return "Poor"
        else:
            return "Critical"


class LLMSummarizer(ReportSummarizer):
    """
    LLM-based summarizer for rich, contextual summaries.
    
    Uses an external LLM API to generate natural language summaries
    with better narrative flow and context awareness.
    
    Falls back to SimpleTemplateSummarizer if LLM unavailable.
    """
    
    def __init__(self):
        """
        Initialize LLM summarizer.
        
        Args:
            api_endpoint: URL for LLM API
            api_key: Authentication key for API
        """
        super().__init__("LLM-Powered")
        self.fallback = SimpleTemplateSummarizer()
        self.llm_client = OpenRouterClient()
    
    def generate_summary(self, report_data: Dict[str, Any]) -> str:
        """
        Generate LLM-powered summary with fallback.
        
        Attempts to use LLM API, falls back to template if unavailable.
        """
        try:
            summary = self._call_llm_api(report_data)
            return summary
            
        except Exception as e:
            self.logger.warning(f"LLM summarization failed: {e}, using fallback")
            return self.fallback.generate_summary(report_data)
    
    def _call_llm_api(self, report_data: Dict[str, Any]) -> str:
        """
        Call OpenRouter API to generate summary.
        """
        return self.llm_client.chat(json.dumps(report_data))


def get_summarizer(summarizer_type: str = "simple", **kwargs) -> ReportSummarizer:
    """
    Factory function to create summarizer by type.
    
    Args:
        summarizer_type: Type of summarizer ('simple', 'llm')
        **kwargs: Summarizer-specific parameters
        
    Returns:
        ReportSummarizer instance
        
    Raises:
        ValueError: If summarizer_type not recognized
    """
    summarizer_type = summarizer_type.lower()

    logging.getLogger(__name__).info("Using summarizer of type: %s", summarizer_type)
    
    if summarizer_type == 'simple':
        return SimpleTemplateSummarizer()
    elif summarizer_type == 'llm':
        return LLMSummarizer()
    else:
        raise ValueError(f"Unknown summarizer type: {summarizer_type}")
