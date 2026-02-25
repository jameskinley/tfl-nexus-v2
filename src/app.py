import logging
import uvicorn
from dotenv import load_dotenv
import os

from app_provider import app
from mcp_provider import mcp

from commands.api_root import root_handler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


app.get("/", summary="API Root", tags=["System"], status_code=200)(root_handler)

def main():
    load_dotenv()

    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8003"))
    from threading import Thread

    thread = Thread(target=lambda: mcp.run(transport="streamable-http"), daemon=True)
    thread.start()

    uvicorn.run(app, host=host, port=port, log_level="info")
    try:
        thread.join(timeout=1)
    except Exception:
        pass

if __name__ == "__main__":
    main()