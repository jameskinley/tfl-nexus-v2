from fastapi import FastAPI
from data.models import Response
from data import db_models
from data.database import init_db, SessionLocal
from routers import data_imports, journeys, lines, stations, network, system, modes, disruptions, reports
from commands.disruption_polling import DisruptionPollingCommand
from commands.crowding_polling import CrowdingPollingCommand
from commands.network_reporting import NetworkReportingCommand
import logging
import asyncio
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

tags_metadata = [
    {
        "name": "Journeys",
        "description": "Journey planning between stations with multiple optimization strategies. "
                       "Request journey plans as resources using natural semantics."
    },
    {
        "name": "Lines",
        "description": "Transport line information including routes, schedules, and disruption status. "
                       "Access details for tube, overground, DLR, and other TfL lines."
    },
    {
        "name": "Stations",
        "description": "Station search and information including connectivity, crowding, and graph status. "
                       "Query station details and relationships."
    },
    {
        "name": "Disruptions",
        "description": "Service disruption tracking and analysis with historical data. "
                       "Query disruptions across the network with flexible filtering."
    },
    {
        "name": "Reports",
        "description": "Network status reports with AI-powered summaries and historical tracking. "
                       "Generate, retrieve, and manage network health reports."
    },
    {
        "name": "Network",
        "description": "Transport network topology and analysis including graph metrics and visualization. "
                       "Access network-wide crowding information."
    },
    {
        "name": "Data Imports",
        "description": "Data import job management for loading TfL network data. "
                       "Monitor import progress and status."
    },
    {
        "name": "System",
        "description": "System health, statistics, and operational metrics. "
                       "Monitor database state and service availability."
    },
    {
        "name": "Reference Data",
        "description": "Reference data including transport modes and disruption categories. "
                       "Access metadata from TfL API."
    }
]

app = FastAPI(
    title="TfL Nexus API",
    description="""
# Transport for London Network Intelligence API

A comprehensive RESTful API for analyzing, routing, and monitoring the Transport for London network 
with real-time disruption tracking, intelligent journey planning, and network health reporting.

## Key Features

* **Intelligent Journey Planning**: True REST resource-based journey queries
* **Real-time Disruptions**: Automatic polling and storage of service disruptions
* **Network Analysis**: Graph-based network analysis and visualization
* **Crowding Information**: Real-time crowding data for stations and lines
* **AI-Powered Reports**: Optional LLM-generated network status summaries
* **HATEOAS Support**: Hypermedia links for API discoverability

## RESTful Design

This API follows REST principles with:
- Resources identified by URLs
- Standard HTTP methods (GET, POST, PUT, DELETE)
- Hypermedia links (HATEOAS) for navigation
- Consistent response formats with metadata
- Proper status codes

## Data Sources

All data is sourced from the official Transport for London (TfL) Unified API.
    """,
    version="3.0.0",
    openapi_tags=tags_metadata
)

app.include_router(journeys.router)
app.include_router(lines.router)
app.include_router(stations.router)
app.include_router(disruptions.router)
app.include_router(reports.router)
app.include_router(network.router)
app.include_router(data_imports.router)
app.include_router(system.router)
app.include_router(modes.router)

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
    """Background task that polls for crowding data every 900 seconds (15 minutes)"""
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
        
        await asyncio.sleep(900)


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
    logging.info("Crowding polling task started (900s interval)")
    
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
    summary="API Root",
    tags=["System"],
    status_code=200
)
async def root():
    from data.api_models import ResourceResponse
    from data.hateoas import HateoasBuilder
    from pydantic import BaseModel
    
    class ApiRoot(BaseModel):
        title: str
        version: str
        description: str
    
    root_data = ApiRoot(
        title="TfL Nexus API",
        version="3.0.0",
        description="RESTful Transport for London Network Intelligence API"
    )
    
    additional_links = {
        "journeys": "/journeys",
        "lines": "/lines",
        "stations": "/stations",
        "disruptions": "/disruptions",
        "reports": "/reports",
        "network": "/network/topology",
        "data_imports": "/data-imports",
        "system_health": "/system/health",
        "system_statistics": "/system/statistics",
        "modes": "/modes",
        "disruption_categories": "/disruption-categories",
        "docs": "/docs"
    }
    
    links = HateoasBuilder.build_links("/", additional_links)
    
    return ResourceResponse(data=root_data, links=links)