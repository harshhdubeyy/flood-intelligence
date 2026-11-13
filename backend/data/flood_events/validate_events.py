"""Validate normalized event records and identify conservative duplicate candidates."""

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.data.flood_events.schema import EVIDENCE_CATEGORIES, EVENT_FIELDS

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = DATA_DIR / "normalized_events.csv"
DEFAULT_OUTPUT = DATA_DIR / "validated_events.csv"
DUPLICATE_DISTANCE_METERS = 100.0
DUPLICATE_TIME_SECONDS = 60 * 60


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _distance_meters(first: Dict[str, Any], second: Dict[str, Any]) -> float:
    lat1, lon1 = math.radians(float(first["latitude"])), math.radians(float(first["longitude"]))
    lat2, lon2 = math.radians(float(second["latitude"])), math.radians(float(second["longitude"]))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def _potential_duplicate_groups(events: List[Dict[str, Any]]) -> List[List[int]]:
    parent = list(range(len(events)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    cell_degrees = 0.001
    buckets: Dict[Tuple[int, int, int], List[int]] = {}
    timestamps = [_timestamp(event.get("event_timestamp")) for event in events]
    for index, event in enumerate(events):
        latitude = _number(event.get("latitude"))
        longitude = _number(event.get("longitude"))
        timestamp = timestamps[index]
        if latitude is None or longitude is None or timestamp is None:
            continue
        lat_cell = math.floor(latitude / cell_degrees)
        lon_scale = max(0.1, math.cos(math.radians(latitude)))
        lon_cell_size = cell_degrees / lon_scale
        lon_cell = math.floor(longitude / lon_cell_size)
        time_cell = int(timestamp.timestamp() // DUPLICATE_TIME_SECONDS)
        for lat_offset in (-1, 0, 1):
            for lon_offset in (-1, 0, 1):
                for time_offset in (-1, 0, 1):
                    key = (lat_cell + lat_offset, lon_cell + lon_offset, time_cell + time_offset)
                    for other_index in buckets.get(key, []):
                        if events[index].get("source_name") == events[other_index].get("source_name"):
                            continue
                        other_timestamp = timestamps[other_index]
                        if other_timestamp is None:
                            continue
                        if abs((timestamp - other_timestamp).total_seconds()) > DUPLICATE_TIME_SECONDS:
                            continue
                        if _distance_meters(event, events[other_index]) <= DUPLICATE_DISTANCE_METERS:
                            union(index, other_index)
        buckets.setdefault((lat_cell, lon_cell, time_cell), []).append(index)

    groups: Dict[int, List[int]] = {}
    for index in range(len(events)):
        root = find(index)
        groups.setdefault(root, []).append(index)
    return [members for members in groups.values() if len(members) > 1]


def validate_events(
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
    duplicate_groups_path: Path = DATA_DIR / "potential_duplicate_groups.csv",
) -> Dict[str, Any]:
    with input_path.open(newline="", encoding="utf-8") as file:
        events = list(csv.DictReader(file))
    errors = 0
    seen_ids = set()
    for event in events:
        issues: List[str] = []
        event_id = event.get("event_id")
        if not event_id:
            issues.append("missing_event_id")
        elif event_id in seen_ids:
            issues.append("duplicate_event_id")
        else:
            seen_ids.add(event_id)
        if not event.get("source_name"):
            issues.append("missing_source_name")
        if not event.get("source_url"):
            issues.append("missing_source_url")
        if not event.get("event_timestamp"):
            issues.append("missing_event_timestamp")

        latitude = _number(event.get("latitude"))
        longitude = _number(event.get("longitude"))
        if event.get("latitude") and latitude is None:
            issues.append("invalid_latitude")
        if event.get("longitude") and longitude is None:
            issues.append("invalid_longitude")
        if latitude is not None and not -90 <= latitude <= 90:
            issues.append("latitude_out_of_range")
        if longitude is not None and not -180 <= longitude <= 180:
            issues.append("longitude_out_of_range")
        if event.get("event_timestamp"):
            try:
                timestamp = datetime.fromisoformat(event["event_timestamp"].replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    issues.append("event_timestamp_missing_timezone")
            except ValueError:
                issues.append("invalid_event_timestamp")
        for field in ("water_depth_m", "duration_minutes", "confidence"):
            if event.get(field):
                value = _number(event[field])
                if value is None:
                    issues.append(f"invalid_{field}")
                elif field != "confidence" and value < 0:
                    issues.append(f"negative_{field}")
                elif field == "confidence" and not 0 <= value <= 1:
                    issues.append("confidence_out_of_range")
        evidence_category = event.get("evidence_category")
        if evidence_category and evidence_category not in EVIDENCE_CATEGORIES:
            issues.append("invalid_evidence_category")

        existing_issues = event.get("validation_issues")
        if existing_issues:
            try:
                issues.extend(json.loads(existing_issues))
            except (TypeError, json.JSONDecodeError):
                issues.append(str(existing_issues))
        event["validation_issues"] = json.dumps(sorted(set(issues))) if issues else None
        event["geospatial_match_confidence"] = (
            event.get("geospatial_match_confidence") or None
        )
        if issues:
            errors += 1

    duplicate_groups = _potential_duplicate_groups(events)
    for event in events:
        event["duplicate_candidate"] = "false"
    duplicate_membership: Dict[int, str] = {}
    for group_number, members in enumerate(duplicate_groups, start=1):
        group_id = f"candidate-{group_number:05d}"
        for index in members:
            duplicate_membership[index] = group_id
            events[index]["duplicate_candidate"] = "true"

    output_fields = [*EVENT_FIELDS, "duplicate_candidate"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(events)

    duplicate_groups_path.parent.mkdir(parents=True, exist_ok=True)
    with duplicate_groups_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=("duplicate_group_id", "event_id", "source_name"),
        )
        writer.writeheader()
        for index, group_id in sorted(duplicate_membership.items()):
            writer.writerow(
                {
                    "duplicate_group_id": group_id,
                    "event_id": events[index].get("event_id"),
                    "source_name": events[index].get("source_name"),
                }
            )
    return {
        "records": len(events),
        "records_with_validation_issues": errors,
        "potential_duplicate_groups": len(duplicate_groups),
        "potential_duplicate_records": sum(len(group) for group in duplicate_groups),
        "output": str(output_path),
        "duplicate_groups_output": str(duplicate_groups_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--duplicate-groups",
        type=Path,
        default=DATA_DIR / "potential_duplicate_groups.csv",
    )
    args = parser.parse_args()
    print(json.dumps(validate_events(args.input, args.output, args.duplicate_groups), indent=2))


if __name__ == "__main__":
    main()
