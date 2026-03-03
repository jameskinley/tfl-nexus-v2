import pytest
from unittest.mock import patch, MagicMock

from data.report_summarizer import (
    SimpleTemplateSummarizer,
    LLMSummarizer,
    get_summarizer,
)


BASE_REPORT = {
    "timestamp": "2026-03-02T12:00:00",
    "report_type": "snapshot",
    "total_disruptions": 0,
    "active_lines_count": 10,
    "affected_lines_count": 0,
    "average_reliability_score": 95.0,
    "graph_metrics": {"nodes": 270, "edges": 300, "components": 1},
    "line_statuses": {},
    "disruption_breakdown": {},
}


class TestGetReliabilityStatus:
    def test_100_returns_excellent(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._get_reliability_status(100.0)

        assert result == "Excellent"

    def test_exactly_95_returns_excellent(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._get_reliability_status(95.0)

        assert result == "Excellent"

    def test_94_returns_good(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._get_reliability_status(94.0)

        assert result == "Good"

    def test_exactly_85_returns_good(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._get_reliability_status(85.0)

        assert result == "Good"

    def test_84_returns_fair(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._get_reliability_status(84.0)

        assert result == "Fair"

    def test_exactly_70_returns_fair(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._get_reliability_status(70.0)

        assert result == "Fair"

    def test_69_returns_poor(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._get_reliability_status(69.0)

        assert result == "Poor"

    def test_exactly_50_returns_poor(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._get_reliability_status(50.0)

        assert result == "Poor"

    def test_49_returns_critical(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._get_reliability_status(49.0)

        assert result == "Critical"

    def test_zero_returns_critical(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._get_reliability_status(0.0)

        assert result == "Critical"


class TestFormatTimestamp:
    def test_valid_iso_string_formatted(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._format_timestamp("2026-03-02T12:30:00")

        assert "2026-03-02" in result
        assert "12:30:00" in result

    def test_z_suffix_handled_without_error(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._format_timestamp("2026-03-02T12:30:00Z")

        assert "2026-03-02" in result

    def test_invalid_string_returns_original(self):
        summarizer = SimpleTemplateSummarizer()

        result = summarizer._format_timestamp("not-a-date")

        assert result == "not-a-date"


class TestSimpleTemplateSummarizerGenerateSummary:
    def test_zero_disruptions_shows_good_service_message(self):
        summarizer = SimpleTemplateSummarizer()
        report = {**BASE_REPORT, "total_disruptions": 0}

        result = summarizer.generate_summary(report)

        assert "Good Service" in result

    def test_with_disruptions_shows_disruption_count(self):
        summarizer = SimpleTemplateSummarizer()
        report = {
            **BASE_REPORT,
            "total_disruptions": 3,
            "affected_lines_count": 2,
            "disruption_breakdown": {"Minor Delays": 3},
            "line_statuses": {"Central": "Minor Delays", "Victoria": "Good Service"},
        }

        result = summarizer.generate_summary(report)

        assert "3" in result

    def test_reliability_score_included_in_output(self):
        summarizer = SimpleTemplateSummarizer()
        report = {**BASE_REPORT, "average_reliability_score": 87.5}

        result = summarizer.generate_summary(report)

        assert "87.5" in result

    def test_network_fragmentation_warning_shown_for_multiple_components(self):
        summarizer = SimpleTemplateSummarizer()
        report = {
            **BASE_REPORT,
            "graph_metrics": {"nodes": 270, "edges": 298, "components": 3},
        }

        result = summarizer.generate_summary(report)

        assert "fragment" in result.lower() or "component" in result.lower()


class TestGetSummarizer:
    def test_simple_returns_simple_template_summarizer(self):
        result = get_summarizer("simple")

        assert isinstance(result, SimpleTemplateSummarizer)

    def test_llm_returns_llm_summarizer(self):
        result = get_summarizer("llm")

        assert isinstance(result, LLMSummarizer)

    def test_unknown_type_raises_value_error(self):
        with pytest.raises(ValueError):
            get_summarizer("unknown_type")

    def test_case_insensitive_simple(self):
        result = get_summarizer("SIMPLE")

        assert isinstance(result, SimpleTemplateSummarizer)


class TestLLMSummarizerFallback:
    def test_falls_back_to_template_when_llm_raises(self):
        summarizer = LLMSummarizer()
        with patch.object(summarizer.llm_client, "chat", side_effect=Exception("LLM unavailable")):
            template_result = summarizer.fallback.generate_summary(BASE_REPORT)

            llm_result = summarizer.generate_summary(BASE_REPORT)

        assert llm_result == template_result
