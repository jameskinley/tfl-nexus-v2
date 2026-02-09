#!/usr/bin/env python
"""
Database initialization script for TfL Nexus

Usage:
    python src/init_db.py              # Drop all tables and recreate (default)
    python src/init_db.py --no-drop    # Keep existing data, only create missing tables
"""
import sys
import argparse
from data.database import init_db, drop_all_tables, engine
from data.db_models import Base
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Initialize TfL Nexus database')
    parser.add_argument(
        '--no-drop',
        action='store_true',
        help='Do NOT drop existing tables (keep existing data)'
    )
    parser.add_argument(
        '--show-tables',
        action='store_true',
        help='Show all tables that will be created'
    )
    
    args = parser.parse_args()
    
    if args.show_tables:
        logger.info("Tables that will be created:")
        for table in Base.metadata.tables.keys():
            logger.info(f"  - {table}")
        return
    
    if not args.no_drop:
        logger.info("Dropping all existing tables...")
        drop_all_tables()
        logger.info("All tables dropped")
    else:
        logger.info("Skipping drop - keeping existing data")
    
    logger.info("Creating database tables...")
    init_db()
    logger.info("✅ Database initialized successfully!")
    logger.info(f"Database location: {engine.url}")
    logger.info("\nNext steps:")
    logger.info("  1. Start the API server: uvicorn src.app:app --reload")
    logger.info("  2. Call the ingest endpoint: curl -X POST http://localhost:8000/route/ingest")
    logger.info("  3. Check stats: curl http://localhost:8000/stats")


if __name__ == "__main__":
    main()
