import asyncio
import logging
from data.database import SessionLocal
from commands.network_reporting import NetworkReportingCommand
from data import db_models
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


async def _generate_daily_reports_background():
    while True:
        try:
            db_session = SessionLocal()
            try:
                if db_session.query(db_models.NetworkReport).filter(
                    db_models.NetworkReport.timestamp >= datetime.now() - timedelta(hours=24)
                ).count() > 0:
                    logger.info("Daily report already generated in the last 24 hours, skipping.")
                else:
                    reporting_command = NetworkReportingCommand(db_session)
                    report = reporting_command.generate_report(report_type='daily_summary')
                    logger.info(f"Daily report generated: {report['id']}")
            finally:
                db_session.close()
        except Exception as e:
            logger.error(f"Error in report generation task: {e}", exc_info=True)

        await asyncio.sleep(86400)


def start(app):
    task = asyncio.create_task(_generate_daily_reports_background())
    setattr(app.state, "report_generation_task", task)
    logger.info("Daily report generation task started (24h interval)")


async def stop(app):
    task = getattr(app.state, "report_generation_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("Report generation task stopped")
