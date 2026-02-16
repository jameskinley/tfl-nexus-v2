from fastapi import FastAPI
from data.models import Response
from data import db_models
from data.database import init_db, SessionLocal
from routers import ingestion, routes, lines, stations, graph, stats, meta, disruptions, reports
from commands.disruption_polling import DisruptionPollingCommand
from commands.crowding_polling import CrowdingPollingCommand
from commands.network_reporting import NetworkReportingCommand
import logging
import asyncio
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

tags_metadata = [
    {
        "name": "Data Ingestion",
        "description": "Data ingestion operations for loading TfL network data into the database. "
                       "Initialize and populate the system with transport network information."
    },
    {
        "name": "Routing",
        "description": "Journey planning and route calculation with multiple optimization strategies. "
                       "Supports fastest path, robust routing, low-crowding, and ML-powered hybrid modes."
    },
    {
        "name": "Lines",
        "description": "Transport line information including routes, schedules, and disruption status. "
                       "Access details for tube, overground, DLR, and other TfL lines."
    },
    {
        "name": "Stations",
        "description": "Station search and information including connectivity and graph status. "
                       "Query station details and check routing graph inclusion."
    },
    {
        "name": "Graph",
        "description": "Transport network graph operations including statistics and visualization. "
                       "Analyze network topology and generate visual representations."
    },
    {
        "name": "Stats",
        "description": "Database statistics and system metrics. "
                       "Monitor data completeness and system health."
    },
    {
        "name": "Meta",
        "description": "TfL API metadata including modes, disruption categories, and stop points. "
                       "Access reference data and system configuration information."
    },
    {
        "name": "Disruptions",
        "description": "Service disruption tracking and analysis. "
                       "Query active disruptions affecting transport lines and stations."
    },
    {
        "name": "Reports",
        "description": "Network status reports with AI-powered summaries. "
                       "Generate, retrieve, and manage network health reports with optional LLM summaries."
    }
]

app = FastAPI(
    title="TfL Nexus API",
    description="""
# Transport for London Network Intelligence API

A comprehensive API for analyzing, routing, and monitoring the Transport for London network 
with real-time disruption tracking, intelligent journey planning, and network health reporting.

## Key Features

* **Intelligent Route Planning**: Multiple optimization strategies (fastest, robust, low-crowding, ML-hybrid)
* **Real-time Disruptions**: Automatic polling and storage of service disruptions
* **Network Analysis**: Graph-based network analysis and visualization
* **Crowding Information**: Real-time crowding data for stations and lines
* **AI-Powered Reports**: Optional LLM-generated network status summaries
* **Comprehensive Data**: Lines, stations, routes, schedules, and stop points

## Data Sources

All data is sourced from the official Transport for London (TfL) Unified API.

## Getting Started

1. Initialize the database with `/ingestion/start`
2. Check ingestion status with `/ingestion/status`
3. Explore lines, stations, and routes using the respective endpoints
4. Calculate optimal routes with `/routes/{from}/{to}`
    """,
    version="2.0.0",
    openapi_tags=tags_metadata
)

app.include_router(ingestion.router)
app.include_router(routes.router)
app.include_router(lines.router)
app.include_router(stations.router)
app.include_router(graph.router)
app.include_router(stats.router)
app.include_router(meta.router)
app.include_router(disruptions.router)
app.include_router(reports.router)

disruption_command = DisruptionPollingCommand()
polling_task = None
crowding_polling_task = None
report_generation_task = None


async def poll_disruptions_background():
    """Background task that polls for disruptions every 120 seconds"""
    while True:
        try:
            db_session = SessionLocal()
            try:
                result = disruption_command.poll_and_store_disruptions(db_session)
                logging.info(f"Disruption polling result: {result}")
            finally:
                db_session.close()
        except Exception as e:
            logging.error(f"Error in disruption polling task: {e}", exc_info=True)
        
        await asyncio.sleep(120)


async def poll_crowding_background():
    """Background task that polls for crowding data every 300 seconds (5 minutes)"""
    while True:
        try:
            db_session = SessionLocal()
            try:
                crowding_command = CrowdingPollingCommand(db_session)
                result = crowding_command.poll_and_update()
                logging.info(f"Crowding polling result: {result}")
            finally:
                db_session.close()
        except Exception as e:
            logging.error(f"Error in crowding polling task: {e}", exc_info=True)
        
        await asyncio.sleep(300)


async def generate_daily_reports_background():
    """Background task that generates daily network reports every 24 hours"""
    while True:
        try:
            db_session = SessionLocal()
            try:
                if db_session.query(db_models.NetworkReport).filter(
                    db_models.NetworkReport.timestamp >= datetime.now() - timedelta(hours=24)
                ).count() > 0:
                    logging.info("Daily report already generated in the last 24 hours, skipping.")
                else:
                    reporting_command = NetworkReportingCommand(db_session)
                    report = reporting_command.generate_report(report_type='daily_summary')
                    logging.info(f"Daily report generated: {report['id']}")
            finally:
                db_session.close()
        except Exception as e:
            logging.error(f"Error in report generation task: {e}", exc_info=True)
        
        # Sleep for 24 hours
        await asyncio.sleep(86400)


@app.on_event("startup")
async def startup_event():
    global polling_task, crowding_polling_task, report_generation_task
    init_db()
    logging.info("Database initialized")
    
    # Start disruption polling task
    polling_task = asyncio.create_task(poll_disruptions_background())
    logging.info("Disruption polling task started (120s interval)")
    
    # Start crowding polling task
    crowding_polling_task = asyncio.create_task(poll_crowding_background())
    logging.info("Crowding polling task started (300s interval)")
    
    # Start daily report generation task
    report_generation_task = asyncio.create_task(generate_daily_reports_background())
    logging.info("Daily report generation task started (24h interval)")


@app.on_event("shutdown")
async def shutdown_event():
    if polling_task:
        polling_task.cancel()
        logging.info("Disruption polling task stopped")
    
    if crowding_polling_task:
        crowding_polling_task.cancel()
        logging.info("Crowding polling task stopped")
    
    if report_generation_task:
        report_generation_task.cancel()
        logging.info("Report generation task stopped")


@app.get(
    "/",
    response_model=Response,
    status_code=200,
    summary="Health Check",
    tags=["Health"],
    responses={
        200: {
            "description": "API is healthy and operational",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "health is wealth"
                    }
                }
            }
        }
    }
)
async def root() -> Response:
    """
    Health check endpoint to verify API availability.
    
    Returns a simple status response indicating the service is running and healthy.
    Use this endpoint to monitor API availability and service health.
    
    Returns:
        Response: Status message confirming API health.
    """
    return Response(status="success", message="health is wealth")