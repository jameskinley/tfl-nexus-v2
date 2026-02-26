import logging
from data.database import init_db
from tasks import disruptions, crowding, reports


async def startup_event(app):
    """Initialise DB and start background tasks (used when called explicitly)."""
    init_db()
    logging.info("Database initialised")
    disruptions.start(app)
    crowding.start(app)
    reports.start(app)


async def shutdown_event(app):
    await disruptions.stop(app)
    await crowding.stop(app)
    await reports.stop(app)