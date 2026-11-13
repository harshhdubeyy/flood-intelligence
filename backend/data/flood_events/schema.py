"""Canonical event fields and conservative source-record normalization."""

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

EVENT_FIELDS = (
    "event_id",
    "source_record_id",
    "source_sha256",
    "source_timezone",
    "event_timestamp",
    "latitude",
    "longitude",
    "ward_id",
    "spatial_ward_id",
    "location_description",
    "event_type",
    "flood_severity",
    "water_depth_m",
    "duration_minutes",
    "source_name",
    "source_url",
    "verification_status",
    "evidence_category",
    "confidence",
    "collection_timestamp",
    "geospatial_match_confidence",
    "ward_match_method",
    "validation_issues",
)
MAPPING_FIELDS = frozenset(EVENT_FIELDS)
EVIDENCE_CATEGORIES = frozenset(
    {
        "citizen_submitted",
        "operator_confirmed_citizen",
        "independently_verified_historical",
        "officially_confirmed_historical",
    }
)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip().lower() in {"", "na", "n/a", "null", "none", "-"}


def _number(value: Any) -> Optional[float]:
    if _is_missing(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _timestamp(
    value: Any,
    source_timezone: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    if _is_missing(value):
        return None, "missing_event_timestamp"
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None, "invalid_event_timestamp"
    if parsed.tzinfo is None:
        if not source_timezone:
            return None, "event_timestamp_missing_timezone"
        try:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            zone = ZoneInfo(source_timezone)
        except (ValueError, ZoneInfoNotFoundError):
            return None, "invalid_source_timezone"
        first = parsed.replace(tzinfo=zone, fold=0)
        second = parsed.replace(tzinfo=zone, fold=1)
        first_round_trip = first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        second_round_trip = second.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        first_valid = first_round_trip == parsed
        second_valid = second_round_trip == parsed
        if not first_valid and not second_valid:
            return None, "nonexistent_local_event_timestamp"
        if first_valid and second_valid and first.utcoffset() != second.utcoffset():
            return None, "ambiguous_local_event_timestamp"
        parsed = first
    return parsed.astimezone(timezone.utc).isoformat(), None


def _event_id(source_name: str, source_record_id: Any, source_record: Dict[str, Any]) -> str:
    if not _is_missing(source_record_id):
        identity = f"{source_name}\0{str(source_record_id).strip()}"
    else:
        canonical_record = json.dumps(source_record, sort_keys=True, ensure_ascii=False, default=str)
        identity = f"{source_name}\0{canonical_record}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def normalize_record(
    source_record: Dict[str, Any],
    source_name: str,
    source_url: str,
    field_mapping: Dict[str, str],
    collected_at: Optional[datetime] = None,
    source_timezone: Optional[str] = None,
    source_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """Map only explicitly configured source fields; unknown values stay null."""
    collection_timestamp = collected_at or datetime.now(timezone.utc)

    def mapped(field: str) -> Any:
        source_field = field_mapping.get(field)
        return source_record.get(source_field) if source_field else None

    latitude = _number(mapped("latitude"))
    longitude = _number(mapped("longitude"))
    confidence = _number(mapped("confidence"))
    water_depth_m = _number(mapped("water_depth_m"))
    duration_minutes = _number(mapped("duration_minutes"))
    event_timestamp, timestamp_issue = _timestamp(
        mapped("event_timestamp"),
        source_timezone,
    )
    evidence_category = (
        str(mapped("evidence_category")).strip()
        if not _is_missing(mapped("evidence_category"))
        else None
    )
    validation_issues = [timestamp_issue] if timestamp_issue else []
    if evidence_category and evidence_category not in EVIDENCE_CATEGORIES:
        validation_issues.append("invalid_evidence_category")

    return {
        "event_id": _event_id(source_name, mapped("source_record_id"), source_record),
        "source_record_id": (
            str(mapped("source_record_id")).strip()
            if not _is_missing(mapped("source_record_id")) else None
        ),
        "source_sha256": source_sha256,
        "source_timezone": source_timezone,
        "event_timestamp": event_timestamp,
        "latitude": latitude,
        "longitude": longitude,
        "ward_id": str(mapped("ward_id")).strip() if not _is_missing(mapped("ward_id")) else None,
        "spatial_ward_id": None,
        "location_description": (
            str(mapped("location_description")).strip()
            if not _is_missing(mapped("location_description")) else None
        ),
        "event_type": str(mapped("event_type")).strip() if not _is_missing(mapped("event_type")) else None,
        "flood_severity": (
            str(mapped("flood_severity")).strip()
            if not _is_missing(mapped("flood_severity")) else None
        ),
        "water_depth_m": water_depth_m,
        "duration_minutes": duration_minutes,
        "source_name": source_name,
        "source_url": source_url,
        "verification_status": (
            str(mapped("verification_status")).strip()
            if not _is_missing(mapped("verification_status")) else None
        ),
        "evidence_category": evidence_category,
        "confidence": confidence,
        "collection_timestamp": collection_timestamp.astimezone(timezone.utc).isoformat(),
        "geospatial_match_confidence": None,
        "ward_match_method": None,
        "validation_issues": validation_issues or None,
    }


def write_events(path: str, events: Iterable[Dict[str, Any]]) -> int:
    """Write canonical CSV while retaining a stable field order."""
    import csv

    count = 0
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=EVENT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for event in events:
            writer.writerow(
                {
                    field: json.dumps(event[field], ensure_ascii=False)
                    if isinstance(event.get(field), (list, dict))
                    else event.get(field)
                    for field in EVENT_FIELDS
                }
            )
            count += 1
    return count
