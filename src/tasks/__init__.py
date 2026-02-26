import logging
from contextlib import asynccontextmanager
from data.database import init_db
from . import disruptions, crowding, reports

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    init_db()
    logger.info("Database initialised")

    try:
        disruptions.start(app)
        crowding.start(app)
        reports.start(app)
        yield
    finally:
        try:
            await disruptions.stop(app)
        except Exception:
            logger.exception("Error stopping disruption task")

        try:
            await crowding.stop(app)
        except Exception:
            logger.exception("Error stopping crowding task")

        try:
            await reports.stop(app)
        except Exception:
            logger.exception("Error stopping report task")
