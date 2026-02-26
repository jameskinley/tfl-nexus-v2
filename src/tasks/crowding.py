import asyncio
import logging
from data.database import SessionLocal
from commands.crowding_polling import CrowdingPollingCommand

logger = logging.getLogger(__name__)


async def _poll_crowding_background():
    while True:
        try:
            db_session = SessionLocal()
            try:
                crowding_command = CrowdingPollingCommand(db_session)
                result = crowding_command.poll_and_update()
                logger.info(f"Crowding polling result: {result}")
            finally:
                db_session.close()
        except Exception as e:
            logger.error(f"Error in crowding polling task: {e}", exc_info=True)

        await asyncio.sleep(900)


def start(app):
    task = asyncio.create_task(_poll_crowding_background())
    setattr(app.state, "crowding_task", task)
    logger.info("Crowding polling task started (900s interval)")


async def stop(app):
    task = getattr(app.state, "crowding_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("Crowding polling task stopped")
