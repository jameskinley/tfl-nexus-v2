import pytest
import json
from types import SimpleNamespace
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data.db_models import Base, NetworkReport
from commands.network_reporting import NetworkReportingCommand


@pytest.fixture
def engine():
    e = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    yield e
    e.dispose()


@pytest.fixture
def db_session(engine):
    s = Session(engine)
    yield s
    s.close()


def make_disruption(category, category_description="desc"):
    return SimpleNamespace(category=category, category_description=category_description)


def insert_report(db_session, report_id=None, report_type="snapshot", timestamp=None):
    report_data = {"timestamp": "2026-03-01T12:00:00", "report_type": report_type}
    report = NetworkReport(
        timestamp=timestamp or datetime(2026, 3, 1, 12, 0),
        report_type=report_type,
        report_data=json.dumps(report_data),
        summary_text="Test summary that is long enough to test truncation behavior in get_reports method.",
        total_disruptions=0,
        active_lines_count=5,
        affected_lines_count=0,
        graph_connectivity_score=1.0,
        average_reliability_score=95.0,
    )
    db_session.add(report)
    db_session.commit()
    return report


class TestGetWorstDisruption:
    def test_higher_severity_wins(self, db_session):
        cmd = NetworkReportingCommand(db_session)
        disruptions = [
            make_disruption("MinorDelays"),
            make_disruption("Closure"),
        ]

        result = cmd._get_worst_disruption(disruptions)

        assert result.category == "Closure"

    def test_suspend_has_same_priority_as_closure(self, db_session):
        cmd = NetworkReportingCommand(db_session)
        disruptions = [
            make_disruption("Suspend"),
            make_disruption("MinorDelays"),
        ]

        result = cmd._get_worst_disruption(disruptions)

        assert result.category == "Suspend"

    def test_unknown_category_treated_as_lowest_severity(self, db_session):
        cmd = NetworkReportingCommand(db_session)
        disruptions = [
            make_disruption("UnknownCategory"),
            make_disruption("SevereDelays"),
        ]

        result = cmd._get_worst_disruption(disruptions)

        assert result.category == "SevereDelays"

    def test_single_disruption_returned_directly(self, db_session):
        cmd = NetworkReportingCommand(db_session)
        disruptions = [make_disruption("MinorDelays")]

        result = cmd._get_worst_disruption(disruptions)

        assert result.category == "MinorDelays"

    def test_all_same_severity_returns_first(self, db_session):
        cmd = NetworkReportingCommand(db_session)
        first = make_disruption("MinorDelays")
        disruptions = [first, make_disruption("MinorDelays")]

        result = cmd._get_worst_disruption(disruptions)

        assert result is first


class TestGetReportById:
    def test_existing_id_returns_report_dict(self, db_session):
        report = insert_report(db_session)
        cmd = NetworkReportingCommand(db_session)

        result = cmd.get_report_by_id(report.id)

        assert result is not None
        assert result["id"] == report.id
        assert "data" in result
        assert "metadata" in result

    def test_missing_id_returns_none(self, db_session):
        cmd = NetworkReportingCommand(db_session)

        result = cmd.get_report_by_id(99999)

        assert result is None

    def test_report_data_deserialized_from_json(self, db_session):
        report = insert_report(db_session, report_type="snapshot")
        cmd = NetworkReportingCommand(db_session)

        result = cmd.get_report_by_id(report.id)

        assert isinstance(result["data"], dict)
        assert result["data"]["report_type"] == "snapshot"


class TestGetReports:
    def test_returns_list_of_reports(self, db_session):
        insert_report(db_session)
        cmd = NetworkReportingCommand(db_session)

        result = cmd.get_reports()

        assert isinstance(result, list)
        assert len(result) >= 1

    def test_limit_respected(self, db_session):
        for i in range(5):
            insert_report(db_session)
        cmd = NetworkReportingCommand(db_session)

        result = cmd.get_reports(limit=2)

        assert len(result) == 2

    def test_invalid_start_date_does_not_raise(self, db_session):
        insert_report(db_session)
        cmd = NetworkReportingCommand(db_session)

        result = cmd.get_reports(start_date="not-a-date")

        assert isinstance(result, list)

    def test_report_type_filter_applied(self, db_session):
        insert_report(db_session, report_type="snapshot")
        insert_report(db_session, report_type="daily_summary")
        cmd = NetworkReportingCommand(db_session)

        result = cmd.get_reports(report_type="daily_summary")

        assert all(r["report_type"] == "daily_summary" for r in result)

    def test_summary_truncated_to_200_chars_in_list(self, db_session):
        report = NetworkReport(
            timestamp=datetime(2026, 3, 1, 12, 0),
            report_type="snapshot",
            report_data=json.dumps({}),
            summary_text="A" * 300,
            total_disruptions=0,
            active_lines_count=5,
            affected_lines_count=0,
            graph_connectivity_score=1.0,
            average_reliability_score=95.0,
        )
        db_session.add(report)
        db_session.commit()
        cmd = NetworkReportingCommand(db_session)

        result = cmd.get_reports()

        matching = [r for r in result if r["id"] == report.id]
        assert len(matching[0]["summary"]) <= 203
