import logging
from contextlib import asynccontextmanager
from data.database import init_db, SessionLocal
from data.db_models import APIKey
from dotenv import set_key
from . import disruptions, crowding, reports

logger = logging.getLogger(__name__)


def _seed_default_key() -> None:
    """Create a default admin key on first startup and persist it to .env."""
    from security import create_api_key  # local import avoids circular deps at module load

    db = SessionLocal()
    try:
        if db.query(APIKey).filter(APIKey.is_active == True).first():
            return  # at least one active key already exists
        raw, _ = create_api_key("default", db, is_admin=True)
        set_key(".env", "SEED_API_KEY", raw)
        msg = f"[SECURITY] Generated default admin API key: {raw}"
        logger.info(msg)
        print(msg, flush=True)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app):
    init_db()
    logger.info("Database initialised")
    _seed_default_key()

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
