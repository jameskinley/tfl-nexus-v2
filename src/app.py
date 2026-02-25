import logging

from app_provider import app
from commands.api_root import root_handler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


app.get("/", summary="API Root", tags=["System"], status_code=200)(root_handler)