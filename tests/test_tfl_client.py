import pytest
from unittest.mock import patch, MagicMock

from data.tfl_client import TflClient
from data.models import RouteNode, Route


def make_mock_response(json_data):
    mock = MagicMock()
    mock.json.return_value = json_data
    return mock


class TestParseTimetable:
    def test_empty_response_returns_empty_parsed(self):
        client = TflClient()

        result = client.parse_timetable({})

        assert result == {"schedules": [], "stationIntervals": []}

    def test_missing_timetable_key_returns_empty_parsed(self):
        client = TflClient()

        result = client.parse_timetable({"other_key": "value"})

        assert result["schedules"] == []
        assert result["stationIntervals"] == []

    def test_valid_response_extracts_station_intervals(self):
        client = TflClient()
        response = {
            "timetable": {
                "routes": [{
                    "stationIntervals": [{
                        "id": "0",
                        "intervals": [
                            {"stopId": "940GZZLUALD", "timeToArrival": 0.0},
                            {"stopId": "940GZZLUBNK", "timeToArrival": 2.5},
                        ]
                    }],
                    "schedules": []
                }]
            }
        }

        result = client.parse_timetable(response)

        assert len(result["stationIntervals"]) == 1
        assert result["stationIntervals"][0]["id"] == "0"
        assert len(result["stationIntervals"][0]["intervals"]) == 2

    def test_valid_response_extracts_schedules(self):
        client = TflClient()
        response = {
            "timetable": {
                "routes": [{
                    "stationIntervals": [],
                    "schedules": [{
                        "name": "Monday - Friday",
                        "firstJourney": {"hour": "5", "minute": "30"},
                        "lastJourney": {"hour": "23", "minute": "45"},
                        "periods": [],
                        "knownJourneys": []
                    }]
                }]
            }
        }

        result = client.parse_timetable(response)

        assert len(result["schedules"]) == 1
        assert result["schedules"][0]["name"] == "Monday - Friday"

    def test_route_with_no_station_intervals_key_handled(self):
        client = TflClient()
        response = {
            "timetable": {
                "routes": [{"schedules": []}]
            }
        }

        result = client.parse_timetable(response)

        assert result["stationIntervals"] == []


class TestGetAllLineStatuses:
    def test_empty_line_ids_returns_empty_list(self):
        client = TflClient()

        result = client.get_all_line_statuses([])

        assert result == []

    def test_good_service_severity_filtered_out(self):
        client = TflClient()
        mock_response = [{
            "id": "central",
            "lineStatuses": [{
                "statusSeverity": 10,
                "statusSeverityDescription": "Good Service",
                "validityPeriods": [{"fromDate": "2026-01-01", "toDate": "2026-01-02"}]
            }]
        }]
        with patch("data.tfl_client.request") as mock_req:
            mock_req.return_value.json.return_value = mock_response

            result = client.get_all_line_statuses(["central"])

        assert result == []

    def test_non_good_service_creates_delay_object(self):
        client = TflClient()
        mock_response = [{
            "id": "bakerloo",
            "lineStatuses": [{
                "statusSeverity": 6,
                "statusSeverityDescription": "Minor Delays",
                "reason": "Track fault",
                "disruption": None,
                "validityPeriods": [{"fromDate": "2026-03-01", "toDate": "2026-03-01"}]
            }]
        }]
        with patch("data.tfl_client.request") as mock_req:
            mock_req.return_value.json.return_value = mock_response

            result = client.get_all_line_statuses(["bakerloo"])

        assert len(result) == 1
        assert result[0].line_id == "bakerloo"

    def test_stop_id_extracted_from_station_naptan_field(self):
        client = TflClient()
        mock_response = [{
            "id": "jubilee",
            "lineStatuses": [{
                "statusSeverity": 6,
                "statusSeverityDescription": "Minor Delays",
                "disruption": {
                    "affectedStops": [{"stationNaptan": "940GZZLUWSM", "id": "fallback"}]
                },
                "validityPeriods": [{"fromDate": "2026-03-01", "toDate": "2026-03-01"}]
            }]
        }]
        with patch("data.tfl_client.request") as mock_req:
            mock_req.return_value.json.return_value = mock_response

            result = client.get_all_line_statuses(["jubilee"])

        assert "940GZZLUWSM" in result[0].affected_stops

    def test_stop_id_falls_back_through_fields(self):
        client = TflClient()
        mock_response = [{
            "id": "circle",
            "lineStatuses": [{
                "statusSeverity": 6,
                "statusSeverityDescription": "Minor Delays",
                "disruption": {
                    "affectedStops": [{"naptanId": "940GZZLUCRC"}]
                },
                "validityPeriods": [{"fromDate": "2026-03-01", "toDate": "2026-03-01"}]
            }]
        }]
        with patch("data.tfl_client.request") as mock_req:
            mock_req.return_value.json.return_value = mock_response

            result = client.get_all_line_statuses(["circle"])

        assert "940GZZLUCRC" in result[0].affected_stops


class TestGetStopPointsByMode:
    def test_duplicate_common_names_merged_into_one_station(self):
        client = TflClient()
        mock_response = {
            "stopPoints": [
                {"commonName": "Bank", "naptanId": "940GZZLUBNK", "lat": 51.51, "lon": -0.088},
                {"commonName": "Bank", "naptanId": "940GZZLUBNK2", "lat": 51.51, "lon": -0.088},
            ]
        }
        with patch("data.tfl_client.request") as mock_req:
            mock_req.return_value.json.return_value = mock_response

            result = client.get_stop_points_by_mode(["tube"])

        assert len(result) == 1
        assert "940GZZLUBNK" in result[0].naptan_codes
        assert "940GZZLUBNK2" in result[0].naptan_codes

    def test_unique_names_create_separate_stations(self):
        client = TflClient()
        mock_response = {
            "stopPoints": [
                {"commonName": "Aldgate", "naptanId": "940GZZLUALD", "lat": 51.51, "lon": -0.07},
                {"commonName": "Bank", "naptanId": "940GZZLUBNK", "lat": 51.51, "lon": -0.088},
            ]
        }
        with patch("data.tfl_client.request") as mock_req:
            mock_req.return_value.json.return_value = mock_response

            result = client.get_stop_points_by_mode(["tube"])

        assert len(result) == 2


class TestGetTimetableForRoute:
    def test_duplicate_schedule_names_merged(self):
        client = TflClient()
        parsed_timetable = {
            "schedules": [{"name": "Monday - Friday", "firstJourney": None, "lastJourney": None, "periods": [], "knownJourneys": []}],
            "stationIntervals": [{"id": "0", "intervals": []}]
        }
        with patch.object(client, "get_timetable", return_value={}), \
             patch.object(client, "parse_timetable", return_value=parsed_timetable):

            result = client.get_timetable_for_route("central", ["NAPTAN1", "NAPTAN2"])

        schedule_names = [s["name"] for s in result["schedules"]]
        assert schedule_names.count("Monday - Friday") == 1

    def test_unique_interval_ids_both_included(self):
        client = TflClient()
        first_parsed = {
            "schedules": [],
            "stationIntervals": [{"id": "0", "intervals": []}]
        }
        second_parsed = {
            "schedules": [],
            "stationIntervals": [{"id": "1", "intervals": []}]
        }
        call_count = [0]

        def side_effect(response):
            idx = call_count[0]
            call_count[0] += 1
            return [first_parsed, second_parsed][idx]

        with patch.object(client, "get_timetable", return_value={}), \
             patch.object(client, "parse_timetable", side_effect=side_effect):

            result = client.get_timetable_for_route("central", ["NAP1", "NAP2"])

        interval_ids = [si["id"] for si in result["stationIntervals"]]
        assert "0" in interval_ids
        assert "1" in interval_ids

    def test_failed_origin_fetch_skipped_gracefully(self):
        client = TflClient()
        with patch.object(client, "get_timetable", side_effect=Exception("API error")):

            result = client.get_timetable_for_route("central", ["NAPTAN_FAIL"])

        assert result == {"schedules": [], "stationIntervals": []}


class TestGetValidModes:
    def test_excluded_modes_filtered_out(self):
        client = TflClient()
        mock_response = [
            {"modeName": "tube", "isTflService": True, "isScheduledService": True},
            {"modeName": "bus", "isTflService": True, "isScheduledService": True},
            {"modeName": "taxi", "isTflService": False, "isScheduledService": False},
            {"modeName": "coach", "isTflService": True, "isScheduledService": False},
        ]
        with patch("data.tfl_client.request") as mock_req:
            mock_req.return_value.json.return_value = mock_response

            result = client.get_valid_modes()

        names = [m.name for m in result]
        assert "tube" in names
        assert "bus" not in names
        assert "taxi" not in names
        assert "coach" not in names


class TestUpdateRouteTimesFromTimetable:
    def test_matching_naptan_updates_transition_time(self):
        client = TflClient()
        route = Route(
            route_id="r1",
            route=[RouteNode(ordinal=0, stop_name="Aldgate", stop_naptan="940GZZLUALD", line="central", mode="tube", distance=0, transition_time=0)]
        )
        timetable_data = {
            "stationIntervals": [{"id": "0", "intervals": [
                {"stopId": "940GZZLUALD", "timeToArrival": 3.5}
            ]}]
        }

        client._update_route_times_from_timetable(route, timetable_data)

        assert route.route[0].transition_time == 3.5

    def test_non_matching_naptan_leaves_time_unchanged(self):
        client = TflClient()
        route = Route(
            route_id="r1",
            route=[RouteNode(ordinal=0, stop_name="Aldgate", stop_naptan="940GZZLUALD", line="central", mode="tube", distance=0, transition_time=9.9)]
        )
        timetable_data = {
            "stationIntervals": [{"id": "0", "intervals": [
                {"stopId": "DIFFERENT_NAPTAN", "timeToArrival": 5.0}
            ]}]
        }

        client._update_route_times_from_timetable(route, timetable_data)

        assert route.route[0].transition_time == 9.9

    def test_empty_timetable_data_leaves_route_unchanged(self):
        client = TflClient()
        route = Route(
            route_id="r1",
            route=[RouteNode(ordinal=0, stop_name="Bank", stop_naptan="940GZZLUBNK", line="central", mode="tube", distance=0, transition_time=2.0)]
        )

        client._update_route_times_from_timetable(route, {})

        assert route.route[0].transition_time == 2.0
