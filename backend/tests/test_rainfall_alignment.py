from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.data.flood_events.align_rainfall import (
    Station,
    _window_values,
    align_event,
)


def test_hourly_alignment_excludes_future_and_marks_partial_windows():
    zone = ZoneInfo("Asia/Kolkata")
    station = Station("Station A", 19.1, 72.8)
    station.observations[datetime(2024, 7, 1, 8, tzinfo=zone)] = [2.0]
    station.observations[datetime(2024, 7, 1, 9, tzinfo=zone)] = [3.0]
    station.observations[datetime(2024, 7, 1, 10, tzinfo=zone)] = [4.0]
    station.observations[datetime(2024, 7, 1, 11, tzinfo=zone)] = [100.0]

    one_hour = _window_values(
        station,
        datetime(2024, 7, 1, 10, tzinfo=zone),
        "1h",
        timedelta(hours=1),
        "hourly",
        1,
    )
    three_hours = _window_values(
        station,
        datetime(2024, 7, 1, 10, tzinfo=zone),
        "3h",
        timedelta(hours=3),
        "hourly",
        3,
    )

    assert one_hour["rainfall_1h_mm"] == 4.0
    assert three_hours["rainfall_3h_mm"] == 9.0
    assert three_hours["rainfall_3h_coverage_status"] == "complete"
    assert three_hours["rainfall_3h_mm"] != 109.0


def test_missing_hour_is_null_not_zero_or_partial_total():
    zone = ZoneInfo("Asia/Kolkata")
    station = Station("Station A", 19.1, 72.8)
    station.observations[datetime(2024, 7, 1, 9, tzinfo=zone)] = [2.0]

    result = _window_values(
        station,
        datetime(2024, 7, 1, 10, tzinfo=zone),
        "3h",
        timedelta(hours=3),
        "hourly",
        3,
    )

    assert result["rainfall_3h_mm"] is None
    assert result["rainfall_3h_observed_sum_mm"] == 2.0
    assert result["rainfall_3h_coverage_status"] == "incomplete_missing_observations"


def test_alignment_preserves_evidence_category_and_reports_station_distance():
    zone = ZoneInfo("Asia/Kolkata")
    hourly = Station("hourly", 19.1, 72.8)
    daily = Station("daily", 19.1, 72.8)
    event = {
        "event_id": "event-1",
        "event_timestamp": "2024-07-01T10:00:00+05:30",
        "evidence_category": "operator_confirmed_citizen",
        "source_name": "Citizen report",
        "latitude": "19.1",
        "longitude": "72.8",
        "ward_id": "BMC-A",
    }

    result = align_event(event, {"hourly": hourly}, {"daily": daily}, "Asia/Kolkata")

    assert result["evidence_category"] == "operator_confirmed_citizen"
    assert result["hourly_station_id"] == "hourly"
    assert result["hourly_station_distance_km"] == 0
    assert result["station_distance_basis"] == "event_coordinates"
