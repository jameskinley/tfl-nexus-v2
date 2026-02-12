from fastapi import FastAPI
from data.models import Response
from data.database import init_db
from routers import ingestion, routes, lines, stations, graph, stats, meta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = FastAPI()

app.include_router(ingestion.router)
app.include_router(routes.router)
app.include_router(lines.router)
app.include_router(stations.router)
app.include_router(graph.router)
app.include_router(stats.router)
app.include_router(meta.router)


@app.on_event("startup")
async def startup_event():
    init_db()
    logging.info("Database initialized")


@app.get("/")
async def root() -> Response:
    """
    Health check endpoint to verify API availability.
    
    Returns a simple status response indicating the service is running and healthy.
    
    Returns:
        Response: Status message confirming API health.
    """
    return Response(status="success", message="health is wealth")