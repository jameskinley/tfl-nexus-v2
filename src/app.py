from fastapi import FastAPI
from data.models import Response
from data.database import init_db, SessionLocal
from routers import ingestion, routes, lines, stations, graph, stats, meta, disruptions
from commands.disruption_polling import DisruptionPollingCommand
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

disruption_command = DisruptionPollingCommand()
polling_task = None


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


@app.on_event("startup")
async def startup_event():
    global polling_task
    init_db()
    logging.info("Database initialized")
    
    polling_task = asyncio.create_task(poll_disruptions_background())
    logging.info("Disruption polling task started")


@app.on_event("shutdown")
async def shutdown_event():
    if polling_task:
        polling_task.cancel()
        logging.info("Disruption polling task stopped")


@app.get("/")
async def root() -> Response:
    """
    Health check endpoint to verify API availability.
    
    Returns a simple status response indicating the service is running and healthy.
    
    Returns:
        Response: Status message confirming API health.
    """
    return Response(status="success", message="health is wealth")