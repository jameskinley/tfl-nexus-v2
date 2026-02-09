from fastapi import FastAPI #type: ignore
from data.models import *
from data.data_ingest import DataIngestCommand
from data.tfl_client import TflClient
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = FastAPI()
tfl_client = TflClient()

@app.get("/")
async def root() -> Response:
    return Response(status="success", message="health is wealth")

@app.get("/route/ingest")
async def ingest_data() -> Response:
    # Placeholder for data ingestion logic
    return Response(status="success", message="Data ingested successfully")

@app.get("/route/{from}/{to}")
async def get_route(from_location: str, to_location: str):
    # Placeholder for route calculation logic
    return {"message": f"Route from {from_location} to {to_location} calculated successfully"}

@app.get("/line")
async def get_all_routes():
    """
    Gets all available lines with routes and any current delays.
    """
    return tfl_client.get_lines_with_disruptions(modes=["tube"])

@app.get("/line/{line_id}")
async def get_route_details(line_id: str):
    """
    Gets details for a specific line, including route information and any current delays.
    """
    return {"message": f"Details for line {line_id} retrieved successfully"}

@app.get("/meta/disruption-categories")
async def get_disruption_categories() -> list[str]:
    """
    Gets all valid disruption categories (e.g., "severe", "minor", "planned").
    """
    return tfl_client.get_valid_disruption_categories()

@app.get("/meta/modes")
async def get_modes() -> list[Mode]:
    """
    Gets all valid transport modes (e.g., "bus", "train", "tram").
    """
    return DataIngestCommand().execute()