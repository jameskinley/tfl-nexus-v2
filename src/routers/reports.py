"""
Reports API Router

Provides CRUD endpoints for network status reports.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from data.database import get_db
from commands.network_reporting import NetworkReportingCommand
from data.report_summarizer import get_summarizer
from pydantic import BaseModel
from typing import Optional
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


class CreateReportRequest(BaseModel):
    """Request model for creating a network report"""
    report_type: str = "snapshot"


class UpdateReportRequest(BaseModel):
    """Request model for updating a network report"""
    report_type: Optional[str] = None
    regenerate_summary: bool = False


class ReportResponse(BaseModel):
    """Response model for report data"""
    id: int
    timestamp: str
    report_type: str
    summary: str


class ReportListItem(BaseModel):
    """List item model for reports"""
    id: int
    timestamp: str
    report_type: str
    total_disruptions: int
    active_lines_count: int
    affected_lines_count: int
    graph_connectivity_score: Optional[float]
    average_reliability_score: Optional[float]
    summary: str


@router.post("", response_model=dict)
async def create_report(
    request: CreateReportRequest,
    db: Session = Depends(get_db)
):
    """
    Generate a new network status report.
    
    Args:
        request: Report generation parameters
        db: Database session
        
    Returns:
        Dictionary with report ID, timestamp, type, and summary
        
    Raises:
        HTTPException: If report generation fails
    """
    try:
        command = NetworkReportingCommand(db)
        
        # Select summarizer based on backend configuration
        summarizer = _get_configured_summarizer()
        
        # Generate report
        report = command.generate_report(
            report_type=request.report_type,
            summarizer=summarizer
        )
        
        return report
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("", response_model=list[ReportListItem])
async def list_reports(
    start_date: Optional[str] = Query(None, description="ISO format start date"),
    end_date: Optional[str] = Query(None, description="ISO format end date"),
    report_type: Optional[str] = Query(None, description="Filter by report type"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db)
):
    """
    List network reports with optional filters.
    
    Args:
        start_date: Optional start date filter (ISO format)
        end_date: Optional end date filter (ISO format)
        report_type: Optional report type filter
        limit: Maximum results (1-100)
        offset: Pagination offset
        db: Database session
        
    Returns:
        List of report summaries
        
    Raises:
        HTTPException: If query fails
    """
    try:
        command = NetworkReportingCommand(db)
        reports = command.get_reports(
            start_date=start_date,
            end_date=end_date,
            report_type=report_type,
            limit=limit,
            offset=offset
        )
        
        return reports
        
    except Exception as e:
        logger.error(f"Error listing reports: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list reports: {str(e)}")


@router.get("/{report_id}", response_model=dict)
async def get_report(
    report_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a single report by ID with full details.
    
    Args:
        report_id: Report ID
        db: Database session
        
    Returns:
        Complete report data including metrics and summary
        
    Raises:
        HTTPException: If report not found or query fails
    """
    try:
        command = NetworkReportingCommand(db)
        report = command.get_report_by_id(report_id)
        
        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
        
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get report: {str(e)}")


@router.put("/{report_id}", response_model=dict)
async def update_report(
    report_id: int,
    request: UpdateReportRequest,
    db: Session = Depends(get_db)
):
    """
    Update an existing network report.
    
    Can update report type and optionally regenerate the summary.
    
    Args:
        report_id: Report ID to update
        request: Update parameters
        db: Database session
        
    Returns:
        Updated report data
        
    Raises:
        HTTPException: If report not found or update fails
    """
    try:
        command = NetworkReportingCommand(db)
        
        # Get configured summarizer if regenerating
        summarizer = _get_configured_summarizer() if request.regenerate_summary else None
        
        # Update report
        report = command.update_report(
            report_id=report_id,
            report_type=request.report_type,
            regenerate_summary=request.regenerate_summary,
            summarizer=summarizer
        )
        
        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
        
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update report: {str(e)}")


@router.delete("/{report_id}", response_model=dict)
async def delete_report(
    report_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a network report.
    
    Args:
        report_id: Report ID to delete
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If report not found or deletion fails
    """
    try:
        command = NetworkReportingCommand(db)
        success = command.delete_report(report_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
        
        return {"message": f"Report {report_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete report: {str(e)}")


def _get_configured_summarizer():
    """
    Get summarizer based on backend configuration.
    
    Checks environment variables for LLM configuration:
    - USE_LLM_SUMMARIZER: Set to 'true' to enable LLM
    - LLM_API_ENDPOINT: LLM API endpoint URL
    - LLM_API_KEY: LLM API key
    
    Returns:
        ReportSummarizer instance
    """
    use_llm = os.getenv('USE_LLM_SUMMARIZER', 'false').lower() == 'true'
    
    if use_llm:
        llm_endpoint = os.getenv('LLM_API_ENDPOINT')
        llm_key = os.getenv('LLM_API_KEY')
        
        if llm_endpoint and llm_key:
            logger.info("Using LLM summarizer from backend configuration")
            return get_summarizer(
                "llm",
                api_endpoint=llm_endpoint,
                api_key=llm_key
            )
        else:
            logger.warning("LLM enabled but credentials not configured, falling back to simple")
    
    return get_summarizer("simple")
