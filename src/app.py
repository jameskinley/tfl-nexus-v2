from fastapi import FastAPI
from data.models import Response
from data.database import init_db, SessionLocal
from routers import ingestion, routes, lines, stations, graph, stats, meta, disruptions, reports
from commands.disruption_polling import DisruptionPollingCommand
from commands.crowding_polling import CrowdingPollingCommand
from commands.network_reporting import NetworkReportingCommand
import logging
import asyncio

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = FastAPI()

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


@app.get("/")
async def root() -> Response:
    """
    Health check endpoint to verify API availability.
    
    Returns a simple status response indicating the service is running and healthy.
    
    Returns:
        Response: Status message confirming API health.
    """
    return Response(status="success", message="health is wealth")