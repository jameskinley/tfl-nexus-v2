from mcp_provider import mcp
from data.database import SessionLocal
from data.api_models import ResourceResponse, ReportData, CreateReportRequest
from commands.network_reporting import NetworkReportingCommand
from data.report_summarizer import get_summarizer
from data.hateoas import HateoasBuilder
import os

@mcp.tool(
    name="generate_network_report",
    title="Generate Network Report",
    description="Generates a network report based on current disruptions and network status"
)
async def create_report(request: CreateReportRequest) -> ResourceResponse[ReportData]:
    db = SessionLocal()
    try:
        use_llm = os.getenv('USE_LLM_SUMMARIZER', 'false').lower() == 'true'
        summarizer = get_summarizer('llm' if use_llm else 'simple')
        command = NetworkReportingCommand(db)
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
    finally:
        db.close()
