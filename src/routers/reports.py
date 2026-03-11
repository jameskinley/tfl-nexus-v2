from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from typing import Any
from data.database import get_db
from commands.network_reporting import NetworkReportingCommand
from data.report_summarizer import get_summarizer
from data.api_models import (
    ResourceResponse, CollectionResponse, ReportData,
    CreateReportRequest, UpdateReportRequest, PaginationMeta
)
from data.hateoas import HateoasBuilder
from typing import Optional
import logging
import math
import os

router = APIRouter(prefix="/reports", tags=["Reports"])
logger = logging.getLogger(__name__)


def _get_configured_summarizer():
    use_llm = os.getenv('USE_LLM_SUMMARIZER', 'false').lower() == 'true'
    return get_summarizer('llm' if use_llm else 'simple')

@router.post(
    "",
    response_model=ResourceResponse[ReportData],
    summary="Generate Network Report",
    status_code=201
)
async def create_report(
    request: CreateReportRequest,
    db: Any = Depends(get_db)
) -> ResourceResponse[ReportData]:
    try:
        command = NetworkReportingCommand(db)
        summarizer = _get_configured_summarizer()
        
        report_dict = command.generate_report(
            report_type=request.report_type,
            summarizer=summarizer
        )
        
        report_data = ReportData(
            id=report_dict['id'],
            timestamp=report_dict['timestamp'],
            report_type=report_dict['report_type'],
            summary=report_dict['summary'],
            total_disruptions=report_dict.get('data', {}).get('total_disruptions', 0),
            active_lines_count=report_dict.get('data', {}).get('active_lines_count', 0),
            affected_lines_count=report_dict.get('data', {}).get('affected_lines_count', 0),
            graph_connectivity_score=report_dict.get('data', {}).get('graph_metrics', {}).get('connectivity_score'),
            average_reliability_score=report_dict.get('data', {}).get('graph_metrics', {}).get('average_reliability')
        )
        
        self_href = f"/reports/{report_data.id}"
        links = HateoasBuilder.build_links(self_href, method="POST")
        
        return ResourceResponse(data=report_data, links=links)
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get(
    "",
    response_model=CollectionResponse[ReportData],
    summary="List Network Reports",
    status_code=200
)
async def list_reports(
    start_date: Optional[str] = Query(None, description="ISO format start date"),
    end_date: Optional[str] = Query(None, description="ISO format end date"),
    report_type: Optional[str] = Query(None, description="Filter by report type"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
) -> CollectionResponse[ReportData]:
    try:
        command = NetworkReportingCommand(db)
        
        reports_raw = command.get_reports(
            start_date=start_date,
            end_date=end_date,
            report_type=report_type,
            limit=10000,
            offset=0
        )
        
        total_count = len(reports_raw)
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        reports_page = reports_raw[start_idx:end_idx]
        
        reports = [
            ReportData(
                id=r['id'],
                timestamp=r['timestamp'],
                report_type=r['report_type'],
                summary=r['summary'],
                total_disruptions=r['total_disruptions'],
                active_lines_count=r['active_lines_count'],
                affected_lines_count=r['affected_lines_count'],
                graph_connectivity_score=r.get('graph_connectivity_score'),
                average_reliability_score=r.get('average_reliability_score')
            )
            for r in reports_page
        ]
        
        total_pages = math.ceil(total_count / per_page) if total_count > 0 else 1
        
        query_params = {}
        if start_date:
            query_params['start_date'] = start_date
        if end_date:
            query_params['end_date'] = end_date
        if report_type:
            query_params['report_type'] = report_type
        
        meta = PaginationMeta(
            total=total_count,
            count=len(reports),
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )
        
        links = HateoasBuilder.build_pagination_links(
            "/reports", page, per_page, total_pages, query_params
        )
        
        return CollectionResponse(data=reports, meta=meta, links=links)
    
    except Exception as e:
        logger.error(f"Error listing reports: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list reports: {str(e)}")


@router.get(
    "/{report_id}",
    response_model=ResourceResponse[ReportData],
    summary="Get Report Details",
    status_code=200
)
async def get_report(
    report_id: int = Path(..., description="Report ID"),
    db: Session = Depends(get_db)
) -> ResourceResponse[ReportData]:
    try:
        command = NetworkReportingCommand(db)
        report_dict = command.get_report_by_id(report_id)
        
        if not report_dict:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
        
        report_data = ReportData(
            id=report_dict['id'],
            timestamp=report_dict['timestamp'],
            report_type=report_dict['report_type'],
            summary=report_dict['summary'],
            total_disruptions=report_dict.get('total_disruptions', 0),
            active_lines_count=report_dict.get('active_lines_count', 0),
            affected_lines_count=report_dict.get('affected_lines_count', 0),
            graph_connectivity_score=report_dict.get('graph_connectivity_score'),
            average_reliability_score=report_dict.get('average_reliability_score')
        )
        
        self_href = f"/reports/{report_id}"
        links = HateoasBuilder.build_links(self_href)
        
        return ResourceResponse(data=report_data, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch report: {str(e)}")


@router.put(
    "/{report_id}",
    response_model=ResourceResponse[ReportData],
    summary="Update Report",
    status_code=200
)
async def update_report(
    request: UpdateReportRequest,
    report_id: int = Path(..., description="Report ID"),
    db: Session = Depends(get_db)
) -> ResourceResponse[ReportData]:
    try:
        command = NetworkReportingCommand(db)
        summarizer = _get_configured_summarizer() if request.regenerate_summary else None

        report_dict = command.update_report(
            report_id=report_id,
            report_type=request.report_type,
            regenerate_summary=request.regenerate_summary,
            summarizer=summarizer
        )

        if not report_dict:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        metadata = report_dict.get('metadata', {})
        report_data = ReportData(
            id=report_dict['id'],
            timestamp=str(report_dict['timestamp']),
            report_type=report_dict['report_type'],
            summary=report_dict['summary'],
            total_disruptions=metadata.get('total_disruptions', 0),
            active_lines_count=metadata.get('active_lines_count', 0),
            affected_lines_count=metadata.get('affected_lines_count', 0),
            graph_connectivity_score=metadata.get('graph_connectivity_score'),
            average_reliability_score=metadata.get('average_reliability_score')
        )

        self_href = f"/reports/{report_id}"
        links = HateoasBuilder.build_links(self_href, method="PUT")

        return ResourceResponse(data=report_data, links=links)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update report: {str(e)}")


@router.delete(
    "/{report_id}",
    summary="Delete Report",
    status_code=204
)
async def delete_report(
    report_id: int = Path(..., description="Report ID"),
    db: Session = Depends(get_db)
):
    try:
        command = NetworkReportingCommand(db)
        success = command.delete_report(report_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
        
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete report: {str(e)}")
