import csv
import json
from pathlib import Path

import pytest

from backend.data.flood_events.discover_sources import require_permitted_event_source
from backend.data.flood_events.download_events import download_source
from backend.data.flood_events.normalize_events import normalize_source
from backend.data.flood_events.schema import EVENT_FIELDS, normalize_record
from backend.data.flood_events.validate_events import (
    _potential_duplicate_groups,
    validate_events,
)
from backend.data.flood_events.event_quality_report import build_report


def test_normalization_keeps_unknown_fields_null_and_id_stable():
    source_record = {"incident": "abc", "extra": "not mapped"}
    mapping = {"source_record_id": "incident", "event_type": "not_present"}
    first = normalize_record(source_record, "test-source", "https://example.test", mapping)
    second = normalize_record(source_record, "test-source", "https://example.test", mapping)

    assert first["event_id"] == second["event_id"]
    assert first["event_type"] is None
    assert first["latitude"] is None
    assert set(first) == set(EVENT_FIELDS)


def test_normalization_requires_explicit_timezone_and_normalizes_to_utc():
    source_record = {"incident": "flood-1", "when": "2024-07-01 10:00:00"}
    mapping = {"source_record_id": "incident", "event_timestamp": "when"}
    unzoned = normalize_record(source_record, "test-source", "https://example.test", mapping)
    zoned = normalize_record(
        source_record,
        "test-source",
        "https://example.test",
        mapping,
        source_timezone="Asia/Kolkata",
    )

    assert unzoned["event_timestamp"] is None
    assert "event_timestamp_missing_timezone" in unzoned["validation_issues"]
    assert zoned["event_timestamp"] == "2024-07-01T04:30:00+00:00"
    assert zoned["source_timezone"] == "Asia/Kolkata"


def test_normalization_does_not_guess_dst_ambiguous_or_nonexistent_times():
    mapping = {"event_timestamp": "when"}
    ambiguous = normalize_record(
        {"when": "2024-11-03T01:30:00"},
        "source",
        "https://example.test",
        mapping,
        source_timezone="America/New_York",
    )
    nonexistent = normalize_record(
        {"when": "2024-03-10T02:30:00"},
        "source",
        "https://example.test",
        mapping,
        source_timezone="America/New_York",
    )

    assert ambiguous["event_timestamp"] is None
    assert "ambiguous_local_event_timestamp" in ambiguous["validation_issues"]
    assert nonexistent["event_timestamp"] is None
    assert "nonexistent_local_event_timestamp" in nonexistent["validation_issues"]


def test_geojson_point_is_read_in_longitude_latitude_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "backend.data.flood_events.normalize_events.require_permitted_event_source",
        lambda source_name: {"source_url": "https://example.test/data"},
    )
    source_path = tmp_path / "events.geojson"
    source_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"event": "flood-1"},
                        "geometry": {"type": "Point", "coordinates": [72.8, 19.1]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "normalized.csv"
    count = normalize_source(
        source_path,
        "source",
        "https://example.test/data",
        {"source_record_id": "event"},
        output_path,
    )

    with output_path.open(newline="", encoding="utf-8") as file:
        event = next(csv.DictReader(file))
    assert count == 1
    assert event["longitude"] == "72.8"
    assert event["latitude"] == "19.1"
    raw_archives = list(tmp_path.glob("events.geojson.*.records.jsonl"))
    assert len(raw_archives) == 1
    raw_record = json.loads(raw_archives[0].read_text(encoding="utf-8"))
    assert raw_record["record"]["event"] == "flood-1"
    assert len(raw_record["source_sha256"]) == 64


def test_normalization_preserves_raw_revision_without_overwriting_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "backend.data.flood_events.normalize_events.require_permitted_event_source",
        lambda source_name: {"source_url": "https://example.test/data"},
    )
    source_path = tmp_path / "events.csv"
    source_path.write_text(
        "id,latitude,water_depth_m\nincident-1,19.1,0\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "normalized.csv"
    field_mapping = {
        "source_record_id": "id",
        "latitude": "latitude",
        "water_depth_m": "water_depth_m",
    }

    normalize_source(
        source_path,
        "source",
        "https://example.test/data",
        field_mapping,
        output_path,
    )
    assert normalize_source(
        source_path,
        "source",
        "https://example.test/data",
        field_mapping,
        output_path,
    ) == 1
    original_output = output_path.read_text(encoding="utf-8")
    source_path.write_text(
        "id,latitude,water_depth_m\nincident-1,19.2,0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="preserve and review this revision"):
        normalize_source(
            source_path,
            "source",
            "https://example.test/data",
            field_mapping,
            output_path,
        )

    assert output_path.read_text(encoding="utf-8") == original_output
    assert len(list(tmp_path.glob("events.csv.*.records.jsonl"))) == 3


def test_json_normalizer_fails_instead_of_silently_discarding_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "backend.data.flood_events.normalize_events.require_permitted_event_source",
        lambda source_name: {"source_url": "https://example.test/data"},
    )
    source_path = tmp_path / "events.json"
    source_path.write_text(json.dumps([{"id": 1}, "not-an-object"]), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON record 2 is not an object"):
        from backend.data.flood_events.normalize_events import _records

        list(_records(source_path))


def test_duplicate_candidates_require_distinct_sources_and_close_events():
    events = [
        {
            "source_name": "A",
            "latitude": "19.1",
            "longitude": "72.8",
            "event_timestamp": "2024-07-01T10:00:00+05:30",
        },
        {
            "source_name": "B",
            "latitude": "19.1001",
            "longitude": "72.8001",
            "event_timestamp": "2024-07-01T10:30:00+05:30",
        },
        {
            "source_name": "A",
            "latitude": "19.1001",
            "longitude": "72.81",
            "event_timestamp": "2024-07-01T10:30:00+05:30",
        },
        {
            "source_name": "C",
            "latitude": "19.1",
            "longitude": "72.8",
            "event_timestamp": "2024-07-01T10:00:00",
        },
    ]

    assert _potential_duplicate_groups(events) == [[0, 1]]


def test_validation_keeps_records_and_flags_unzoned_timestamps(tmp_path: Path):
    input_path = tmp_path / "events.csv"
    output_path = tmp_path / "validated.csv"
    duplicate_path = tmp_path / "duplicates.csv"
    event = {field: None for field in EVENT_FIELDS}
    event.update(
        {
            "event_id": "one",
            "event_timestamp": "2024-07-01T10:00:00",
            "latitude": "19.1",
            "longitude": "72.8",
            "source_name": "source",
            "source_url": "https://example.test",
        }
    )
    with input_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerow(event)

    result = validate_events(input_path, output_path, duplicate_path)
    with output_path.open(newline="", encoding="utf-8") as file:
        validated = next(csv.DictReader(file))
    assert result["records"] == 1
    assert result["records_with_validation_issues"] == 1
    assert "event_timestamp_missing_timezone" in validated["validation_issues"]
    assert validated["duplicate_candidate"] == "false"


def test_quality_report_shows_all_wards_and_no_ml_readiness():
    wards = [
        {
            "ward_id": f"W-{index:02}",
            "ward_name": f"Ward {index}",
            "geometry_valid": True,
            "geometry_srid": 4326,
        }
        for index in range(24)
    ]

    report = build_report([], wards, {"potential_duplicate_groups": 0, "potential_duplicate_records": 0})

    assert report["event_counts"]["total_records"] == 0
    assert report["geographic_coverage"]["registered_ward_count"] == 24
    assert report["geographic_coverage"]["wards_with_events"] == 0
    assert all(ward["event_count"] == 0 for ward in report["geographic_coverage"]["ward_distribution"])
    assert report["supervised_ml_readiness"]["ready"] is False


def test_quality_report_counts_spatially_resolved_ward_before_source_ward():
    wards = [
        {
            "ward_id": ward_id,
            "ward_name": ward_id,
            "geometry_valid": True,
            "geometry_srid": 4326,
        }
        for ward_id in ("W-01", "W-02")
    ]
    events = [
        {
            "event_id": "event-1",
            "ward_id": "W-02",
            "spatial_ward_id": "W-01",
            "evidence_category": "officially_confirmed_historical",
        }
    ]

    report = build_report(
        events,
        wards,
        {"potential_duplicate_groups": 0, "potential_duplicate_records": 0},
    )

    by_ward = {
        ward["ward_id"]: ward
        for ward in report["geographic_coverage"]["ward_distribution"]
    }
    assert by_ward["W-01"]["event_count"] == 1
    assert by_ward["W-01"]["officially_confirmed_count"] == 1
    assert by_ward["W-02"]["event_count"] == 0


def test_quality_report_keeps_prospective_reports_separate_from_historical_labels():
    operational_sources = {
        "prospective_citizen_reports": {
            "total_submissions": 41,
            "operator_verification_status_distribution": {"pending": 41},
            "cv_verified_submissions": 1,
            "duplicate_flagged_submissions": 35,
            "not_included_in_historical_event_csv": True,
        },
        "platform_event_records": {
            "records_by_source_status_and_confirmation": [],
            "operator_confirmed_citizen_events": 0,
            "officially_confirmed_records": 0,
            "not_merged_with_historical_event_csv": True,
        },
    }

    report = build_report(
        [],
        [],
        {"potential_duplicate_groups": 0, "potential_duplicate_records": 0},
        operational_sources=operational_sources,
    )

    assert report["event_counts"]["total_records"] == 0
    assert report["event_counts"]["officially_confirmed_historical_records"] == 0
    assert report["operational_sources"]["prospective_citizen_reports"]["total_submissions"] == 41
    assert report["operational_sources"]["platform_event_records"]["officially_confirmed_records"] == 0


def test_downloader_refuses_unverified_source_without_request():
    try:
        download_source("MCGM Disaster Management Department")
    except ValueError as error:
        assert "no request was made" in str(error)
    else:
        raise AssertionError("Unverified source should not be downloaded.")


def test_unpermitted_sources_cannot_be_normalized_as_event_records():
    with pytest.raises(ValueError, match="not catalogued as flood event records"):
        require_permitted_event_source("OpenCity Mumbai Rainfall Data")
