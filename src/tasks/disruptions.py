import asyncio
import logging
from data.database import SessionLocal
from commands.disruption_polling import DisruptionPollingCommand

logger = logging.getLogger(__name__)


async def _poll_disruptions_background():
    cmd = DisruptionPollingCommand()
    while True:
        try:
            db_session = SessionLocal()
            try:
                result = cmd.poll_and_store_disruptions(db_session)
                logger.info(f"Disruption polling result: {result}")
            finally:
                db_session.close()
        except Exception as e:
            logger.error(f"Error in disruption polling task: {e}", exc_info=True)

        await asyncio.sleep(120)


def start(app):
    """Start the disruption polling background task and store it on app.state."""
    task = asyncio.create_task(_poll_disruptions_background())
    setattr(app.state, "disruption_task", task)
    logger.info("Disruption polling task started (120s interval)")


async def stop(app):
    task = getattr(app.state, "disruption_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("Disruption polling task stopped")
