"""Summarize event provenance and coverage without treating rainfall as flood labels."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import get_settings
from backend.data.flood_events.schema import EVENT_FIELDS

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_EVENTS = DATA_DIR / "validated_events.csv"
DEFAULT_REPORT = DATA_DIR / "event_quality_report.json"
DEFAULT_WARD_REPORT = DATA_DIR / "ward_coverage.csv"
DEFAULT_MARKDOWN = DATA_DIR / "DATA_QUALITY_REPORT.md"
DEFAULT_RAINFALL_ALIGNMENT_REPORT = DATA_DIR / "rainfall_alignment_report.json"


def _missing(value: Any) -> bool:
    return value is None or not str(value).strip()


def _load_events(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _read_duplicate_groups(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {"potential_duplicate_groups": 0, "potential_duplicate_records": 0}
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    return {
        "potential_duplicate_groups": len(
            {
                row["duplicate_group_id"]
                for row in rows
                if row.get("duplicate_group_id")
            }
        ),
        "potential_duplicate_records": len(rows),
    }


async def _ward_inventory() -> List[Dict[str, Any]]:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT ward_id, ward_name, ST_IsValid(geom) AS geometry_valid,
                           ST_SRID(geom) AS geometry_srid
                    FROM wards
                    ORDER BY ward_id
                    """
                )
            )
            return [
                {
                    "ward_id": row.ward_id,
                    "ward_name": row.ward_name,
                    "geometry_valid": bool(row.geometry_valid),
                    "geometry_srid": int(row.geometry_srid),
                }
                for row in result
            ]
    finally:
        await engine.dispose()


async def _operational_source_inventory() -> Dict[str, Any]:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            citizen_rows = (
                await session.execute(
                    text(
                        """
                        SELECT operator_verification_status,
                               COUNT(*) AS record_count,
                               COUNT(*) FILTER (WHERE cv_verified) AS cv_verified_count,
                               COUNT(*) FILTER (WHERE is_duplicate) AS duplicate_count
                        FROM citizen_reports
                        GROUP BY operator_verification_status
                        ORDER BY operator_verification_status
                        """
                    )
                )
            ).mappings().all()
            event_rows = (
                await session.execute(
                    text(
                        """
                        SELECT source_kind, verification_status, official_confirmation,
                               COUNT(*) AS record_count
                        FROM flood_events
                        GROUP BY source_kind, verification_status, official_confirmation
                        ORDER BY source_kind, verification_status, official_confirmation
                        """
                    )
                )
            ).mappings().all()
        citizen_status_counts = {
            row["operator_verification_status"]: int(row["record_count"])
            for row in citizen_rows
        }
        citizen_reports = {
            "total_submissions": sum(citizen_status_counts.values()),
            "operator_verification_status_distribution": citizen_status_counts,
            "cv_verified_submissions": sum(
                int(row["cv_verified_count"]) for row in citizen_rows
            ),
            "duplicate_flagged_submissions": sum(
                int(row["duplicate_count"]) for row in citizen_rows
            ),
            "not_included_in_historical_event_csv": True,
        }
        platform_events = [
            {
                "source_kind": row["source_kind"],
                "verification_status": row["verification_status"],
                "official_confirmation": bool(row["official_confirmation"]),
                "record_count": int(row["record_count"]),
            }
            for row in event_rows
        ]
        return {
            "prospective_citizen_reports": citizen_reports,
            "platform_event_records": {
                "records_by_source_status_and_confirmation": platform_events,
                "operator_confirmed_citizen_events": sum(
                    event["record_count"]
                    for event in platform_events
                    if event["source_kind"] == "citizen_report"
                    and event["verification_status"] == "operator_confirmed"
                    and not event["official_confirmation"]
                ),
                "officially_confirmed_records": sum(
                    event["record_count"]
                    for event in platform_events
                    if event["official_confirmation"]
                ),
                "not_merged_with_historical_event_csv": True,
            },
        }
    finally:
        await engine.dispose()


def _validation_issue_count(events: List[Dict[str, str]], fragment: str) -> int:
    count = 0
    for event in events:
        try:
            issues = json.loads(event.get("validation_issues") or "[]")
        except json.JSONDecodeError:
            issues = [event.get("validation_issues") or ""]
        count += any(fragment in issue for issue in issues)
    return count


def build_report(
    events: List[Dict[str, str]],
    wards: List[Dict[str, Any]],
    duplicate_groups: Dict[str, int],
    rainfall_alignment: Dict[str, Any] | None = None,
    operational_sources: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    ward_counts = Counter(
        event.get("spatial_ward_id") or event.get("ward_id")
        for event in events
        if event.get("spatial_ward_id") or event.get("ward_id")
    )
    source_counts = Counter(event.get("source_name") or "unknown" for event in events)
    verification_counts = Counter(
        event.get("verification_status") or "unknown" for event in events
    )
    date_counts = Counter()
    invalid_timestamps = 0
    for event in events:
        timestamp = event.get("event_timestamp")
        if not timestamp:
            continue
        try:
            month = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime("%Y-%m")
            date_counts[month] += 1
        except ValueError:
            invalid_timestamps += 1
    missing_values = {
        field: {
            "null_count": sum(_missing(event.get(field)) for event in events),
            "null_rate": (
                sum(_missing(event.get(field)) for event in events) / len(events)
                if events
                else None
            ),
        }
        for field in EVENT_FIELDS
    }
    unique_event_ids = {event.get("event_id") for event in events if event.get("event_id")}
    categories = Counter(event.get("evidence_category") or "unknown" for event in events)
    official_count = categories.get("officially_confirmed_historical", 0)
    independent_count = categories.get("independently_verified_historical", 0)
    operator_citizen_count = categories.get("operator_confirmed_citizen", 0)
    citizen_submitted_count = categories.get("citizen_submitted", 0)
    unverified_count = sum(
        event.get("evidence_category") not in {
            "operator_confirmed_citizen",
            "independently_verified_historical",
            "officially_confirmed_historical",
        }
        for event in events
    )
    ward_distribution = [
        {
            "ward_id": ward["ward_id"],
            "ward_name": ward["ward_name"],
            "event_count": ward_counts.get(ward["ward_id"], 0),
            "officially_confirmed_count": sum(
                (event.get("spatial_ward_id") or event.get("ward_id")) == ward["ward_id"]
                and event.get("evidence_category") == "officially_confirmed_historical"
                for event in events
            ),
            "independently_verified_count": sum(
                (event.get("spatial_ward_id") or event.get("ward_id")) == ward["ward_id"]
                and event.get("evidence_category") == "independently_verified_historical"
                for event in events
            ),
            "operator_confirmed_citizen_count": sum(
                (event.get("spatial_ward_id") or event.get("ward_id")) == ward["ward_id"]
                and event.get("evidence_category") == "operator_confirmed_citizen"
                for event in events
            ),
        }
        for ward in wards
    ]
    known_ward_ids = {ward["ward_id"] for ward in wards}
    unknown_ward_ids = sorted(set(ward_counts) - known_ward_ids)
    coordinate_records = sum(
        not _missing(event.get("latitude")) and not _missing(event.get("longitude"))
        for event in events
    )
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "event_counts": {
            "total_records": len(events),
            "unique_event_ids": len(unique_event_ids),
            "duplicate_event_ids": len(events) - len(unique_event_ids),
            "unique_source_record_ids": len(
                {
                    (event.get("source_name"), event.get("source_record_id"))
                    for event in events
                    if event.get("source_record_id")
                }
            ),
            "unique_incident_count": None,
            "unique_incident_count_note": (
                "Not asserted: cross-source duplicate candidates have not been adjudicated."
            ),
            "officially_confirmed_historical_records": official_count,
            "independently_verified_historical_records": independent_count,
            "operator_confirmed_citizen_records": operator_citizen_count,
            "citizen_submitted_records": citizen_submitted_count,
            "unverified_records": unverified_count,
        },
        "geographic_coverage": {
            "registered_ward_count": len(wards),
            "wards_with_events": sum(
                ward_counts.get(ward["ward_id"], 0) > 0 for ward in wards
            ),
            "event_records_with_coordinates": coordinate_records,
            "event_records_without_coordinates": len(events) - coordinate_records,
            "event_records_without_resolved_ward": sum(
                not (event.get("spatial_ward_id") or event.get("ward_id"))
                for event in events
            ),
            "ward_distribution": ward_distribution,
            "unregistered_ward_ids": unknown_ward_ids,
            "invalid_registered_ward_geometries": [
                ward["ward_id"] for ward in wards if not ward["geometry_valid"]
            ],
            "registered_geometry_srids": sorted(
                {ward["geometry_srid"] for ward in wards}
            ),
        },
        "date_distribution_by_month": dict(sorted(date_counts.items())),
        "invalid_event_timestamp_count": invalid_timestamps,
        "source_distribution": dict(sorted(source_counts.items())),
        "verification_status_distribution": dict(sorted(verification_counts.items())),
        "evidence_category_distribution": dict(sorted(categories.items())),
        "temporal_coverage": {
            "first_event_timestamp": min(
                (event.get("event_timestamp") for event in events if event.get("event_timestamp")),
                default=None,
            ),
            "last_event_timestamp": max(
                (event.get("event_timestamp") for event in events if event.get("event_timestamp")),
                default=None,
            ),
        },
        "missing_values": missing_values,
        "spatial_review": {
            "records_with_source_spatial_ward_mismatch": _validation_issue_count(
                events, "source_ward_mismatch"
            ),
            "records_outside_registered_wards": _validation_issue_count(
                events, "outside_registered_wards"
            ),
            "records_with_ambiguous_boundary_match": _validation_issue_count(
                events, "multiple_wards"
            ),
            "records_with_validation_issues": sum(
                not _missing(event.get("validation_issues")) for event in events
            ),
        },
        "duplicate_candidates": duplicate_groups,
        "rainfall_alignment": rainfall_alignment or {
            "status": "not_generated",
            "aligned_event_count": 0,
            "complete_coverage_by_window": {},
        },
        "operational_sources": operational_sources or {
            "prospective_citizen_reports": {
                "total_submissions": 0,
                "operator_verification_status_distribution": {},
                "cv_verified_submissions": 0,
                "duplicate_flagged_submissions": 0,
                "not_included_in_historical_event_csv": True,
            },
            "platform_event_records": {
                "records_by_source_status_and_confirmation": [],
                "operator_confirmed_citizen_events": 0,
                "officially_confirmed_records": 0,
                "not_merged_with_historical_event_csv": True,
            },
        },
        "supervised_ml_readiness": {
            "ready": False,
            "assessment": (
                "Not suitable for supervised flood prediction: no event dataset has been "
                "acquired and no independently verified event labels are present. Rainfall "
                "observations and citizen submissions are not substituted for official "
                "historical flood labels."
            ),
            "reasons": [
                "No public, downloadable, time-stamped Mumbai flood incident dataset was verified.",
                "No historical records are explicitly marked officially confirmed."
                if official_count == 0
                else "The current record count and source coverage have not been independently evaluated.",
                "The amount and temporal coverage of event labels are insufficient for temporal validation.",
            ],
        },
    }
    return report


def _write_markdown(report: Dict[str, Any], path: Path) -> None:
    counts = report["event_counts"]
    coverage = report["geographic_coverage"]
    lines = [
        "# Historical flood-event data quality",
        "",
        f"Generated: {report['generated_at_utc']}",
        "",
        "## Dataset",
        "",
        f"- Event records: {counts['total_records']}",
        f"- Unique event IDs: {counts['unique_event_ids']}",
        f"- Unique source record IDs: {counts['unique_source_record_ids']}",
        f"- Officially confirmed historical records: {counts['officially_confirmed_historical_records']}",
        f"- Independently verified historical records: {counts['independently_verified_historical_records']}",
        f"- Operator-confirmed citizen records: {counts['operator_confirmed_citizen_records']}",
        f"- Citizen-submitted records: {counts['citizen_submitted_records']}",
        f"- Unverified records: {counts['unverified_records']}",
        f"- Unique incident count: {counts['unique_incident_count']} "
        f"({counts['unique_incident_count_note']})",
        f"- Potential duplicate groups (not removed): "
        f"{report['duplicate_candidates']['potential_duplicate_groups']}",
        f"- Registered wards checked: {coverage['registered_ward_count']}",
        f"- Wards with events: {coverage['wards_with_events']}",
        f"- Records with coordinates: {coverage['event_records_with_coordinates']}",
        f"- Prospective citizen submissions (separate source): "
        f"{report['operational_sources']['prospective_citizen_reports']['total_submissions']}",
        f"- Operator-confirmed citizen events (separate platform records): "
        f"{report['operational_sources']['platform_event_records']['operator_confirmed_citizen_events']}",
        f"- Officially confirmed platform records: "
        f"{report['operational_sources']['platform_event_records']['officially_confirmed_records']}",
        "",
        "## Ward coverage",
        "",
        "| Ward ID | Ward name | Events |",
        "|---|---|---:|",
    ]
    lines.extend(
        f"| {ward['ward_id']} | {ward['ward_name']} | {ward['event_count']} |"
        for ward in coverage["ward_distribution"]
    )
    lines.extend(
        [
            "",
            "## Supervised-learning assessment",
            "",
            report["supervised_ml_readiness"]["assessment"],
            "",
            "No rainfall observation is interpreted as a flood label. Potential duplicate "
            "groups are review candidates and are not automatically merged.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


async def generate_reports(
    events_path: Path = DEFAULT_EVENTS,
    report_path: Path = DEFAULT_REPORT,
    ward_report_path: Path = DEFAULT_WARD_REPORT,
    markdown_path: Path = DEFAULT_MARKDOWN,
    duplicate_groups_path: Path = DATA_DIR / "potential_duplicate_groups.csv",
    rainfall_alignment_report_path: Path = DEFAULT_RAINFALL_ALIGNMENT_REPORT,
) -> Dict[str, Any]:
    events = _load_events(events_path)
    wards = await _ward_inventory()
    operational_sources = await _operational_source_inventory()
    rainfall_alignment = None
    if rainfall_alignment_report_path.exists():
        rainfall_alignment = json.loads(
            rainfall_alignment_report_path.read_text(encoding="utf-8")
        )
    report = build_report(
        events,
        wards,
        _read_duplicate_groups(duplicate_groups_path),
        rainfall_alignment,
        operational_sources,
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ward_report_path.parent.mkdir(parents=True, exist_ok=True)
    with ward_report_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=(
                "ward_id",
                "ward_name",
                "event_count",
                "officially_confirmed_count",
                "independently_verified_count",
                "operator_confirmed_citizen_count",
            ),
        )
        writer.writeheader()
        writer.writerows(report["geographic_coverage"]["ward_distribution"])
    _write_markdown(report, markdown_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--ward-report", type=Path, default=DEFAULT_WARD_REPORT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument(
        "--duplicate-groups",
        type=Path,
        default=DATA_DIR / "potential_duplicate_groups.csv",
    )
    args = parser.parse_args()
    report = asyncio.run(
        generate_reports(
            args.events,
            args.report,
            args.ward_report,
            args.markdown,
            args.duplicate_groups,
        )
    )
    print(json.dumps(report["event_counts"], indent=2))


if __name__ == "__main__":
    main()
