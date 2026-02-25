from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from .db_models import Base
import os
from logging import getLogger

logger = getLogger(__name__)

env_database_url = os.getenv("DATABASE_URL")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")
db_name = os.getenv("DB_NAME")

if env_database_url:
    DATABASE_URL = env_database_url
elif db_host and db_name and db_user:
    db_password = db_password or ""
    db_port = db_port or "5432"
    DATABASE_URL = f"postgresql+psycopg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
else:
    DATABASE_URL = "sqlite:///tfl_nexus.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    echo=False 
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initialize the database by creating all tables"""
    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    # If using Postgres, attempt to upgrade any timestamp-like columns
    try:
        if engine.dialect.name == 'postgresql':
            from .pg_migrations import upgrade_timestamp_columns

            logger.info("Running Postgres timestamp column upgrades (if needed)")
            upgrade_timestamp_columns(engine)
    except Exception as e:
        logger.warning("Postgres column upgrade step failed: %s", e)
    logger.info("Database initialized successfully")


def drop_all_tables():
    """Drop all tables (use with caution!)"""
    logger.warning("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    logger.warning("All tables dropped")


@contextmanager
def get_db_session():
    """
    Context manager for database sessions.
    
    Usage:
        with get_db_session() as session:
            # perform database operations
            session.commit()
    """
    session = SessionLocal()
    try:
        yield session
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        session.close()


def get_db():
    """
    Dependency for FastAPI routes.
    
    Usage:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            # use db session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
