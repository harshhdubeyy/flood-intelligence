"""Normalize an archived CSV, JSON, or GeoJSON source using explicit field mappings."""

import argparse
import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from backend.data.flood_events.schema import (
    MAPPING_FIELDS,
    normalize_record,
    write_events,
)
from backend.data.flood_events.discover_sources import require_permitted_event_source

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = DATA_DIR / "normalized_events.csv"
NUMERIC_SOURCE_FIELDS = {
    "latitude",
    "longitude",
    "water_depth_m",
    "duration_minutes",
    "confidence",
}


def _same_source_value(field: str, previous: Any, current: Any) -> bool:
    if current is None:
        return previous is None or not str(previous).strip()
    if field in NUMERIC_SOURCE_FIELDS:
        try:
            return float(previous) == float(current)
        except (TypeError, ValueError):
            return False
    return previous == str(current)


def _write_events_atomically(output_path: Path, events: list[Dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        write_events(str(temporary_path), events)
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _records(path: Path) -> Iterator[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as file:
            yield from csv.DictReader(file)
        return

    if suffix not in {".json", ".geojson"}:
        raise ValueError(f"Unsupported input format {suffix!r}; use CSV, JSON, or GeoJSON.")
    with path.open(encoding="utf-8") as file:
        document = json.load(file)
    if isinstance(document, dict) and document.get("type") == "FeatureCollection":
        features = document.get("features")
        if not isinstance(features, list):
            raise ValueError("GeoJSON FeatureCollection must contain a features array.")
        for index, feature in enumerate(features, start=1):
            if not isinstance(feature, dict):
                raise ValueError(f"GeoJSON feature {index} is not an object.")
            if not isinstance(feature.get("properties") or {}, dict):
                raise ValueError(f"GeoJSON feature {index} properties must be an object.")
            properties = dict(feature.get("properties") or {})
            geometry = feature.get("geometry") or {}
            if geometry.get("type") == "Point":
                coordinates = geometry.get("coordinates") or []
                if len(coordinates) >= 2:
                    properties.setdefault("_geojson_longitude", coordinates[0])
                    properties.setdefault("_geojson_latitude", coordinates[1])
            properties["_geojson_original_geometry"] = geometry
            properties["_geojson_feature_id"] = feature.get("id")
            yield properties
        return
    if isinstance(document, list):
        for index, record in enumerate(document, start=1):
            if not isinstance(record, dict):
                raise ValueError(f"JSON record {index} is not an object.")
            yield record
        return
    if isinstance(document, dict) and isinstance(document.get("records"), list):
        for index, record in enumerate(document["records"], start=1):
            if not isinstance(record, dict):
                raise ValueError(f"JSON record {index} is not an object.")
            yield record
        return
    raise ValueError("JSON root must be a record list, a {records: [...]} object, or GeoJSON.")


def normalize_source(
    input_path: Path,
    source_name: str,
    source_url: str,
    field_mapping: Dict[str, str],
    output_path: Path = DEFAULT_OUTPUT,
    raw_archive_path: Optional[Path] = None,
    source_timezone: Optional[str] = None,
) -> int:
    source = require_permitted_event_source(source_name)
    if source.get("source_url") != source_url:
        raise ValueError("Source URL must exactly match the catalogued source URL.")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Source input and normalized output must be separate files.")
    collected_at = datetime.now(timezone.utc)
    normalized = []
    raw_records = []
    input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
    for record in _records(input_path):
        mapped = dict(field_mapping)
        if input_path.suffix.lower() == ".geojson":
            mapped.setdefault("longitude", "_geojson_longitude")
            mapped.setdefault("latitude", "_geojson_latitude")
        normalized.append(
            normalize_record(
                record,
                source_name,
                source_url,
                mapped,
                collected_at,
                source_timezone,
                input_sha256,
            )
        )
        raw_records.append(record)

    if raw_archive_path is None:
        raw_archive_path = input_path.with_name(
            f"{input_path.name}.{collected_at.strftime('%Y%m%dT%H%M%S%fZ')}.records.jsonl"
        )
    raw_archive_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_archive_path.exists():
        raise FileExistsError(f"Raw archive already exists: {raw_archive_path}")

    with raw_archive_path.open("x", encoding="utf-8") as archive:
        for index, record in enumerate(raw_records):
            archive.write(
                json.dumps(
                    {
                        "source_name": source_name,
                        "source_url": source_url,
                        "collected_at": collected_at.isoformat(),
                        "source_sha256": input_sha256,
                        "source_record_number": index + 1,
                        "record": record,
                    },
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
    if output_path.exists():
        with output_path.open(newline="", encoding="utf-8") as file:
            existing = {
                row["event_id"]: row for row in csv.DictReader(file) if row.get("event_id")
            }
    else:
        existing = {}
    source_value_fields = (
        "source_record_id",
        "event_timestamp",
        "latitude",
        "longitude",
        "ward_id",
        "location_description",
        "event_type",
        "flood_severity",
        "water_depth_m",
        "duration_minutes",
        "verification_status",
        "evidence_category",
        "confidence",
    )
    for event in normalized:
        previous = existing.get(event["event_id"])
        if previous:
            conflicts = [
                field
                for field in source_value_fields
                if not _same_source_value(field, previous.get(field), event.get(field))
            ]
            if conflicts:
                raise ValueError(
                    "Source record changed for stable event ID "
                    f"{event['event_id']}; preserve and review this revision before "
                    f"normalizing it. Changed fields: {', '.join(conflicts)}."
                )
            previous["source_sha256"] = event["source_sha256"]
            previous["source_timezone"] = event["source_timezone"]
            previous["collection_timestamp"] = event["collection_timestamp"]
            continue
        existing[event["event_id"]] = event
    _write_events_atomically(output_path, list(existing.values()))
    return len(normalized)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument(
        "--field-map",
        type=Path,
        required=True,
        help="JSON object mapping canonical field names to exact source column names.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--source-timezone",
        help="IANA timezone for source timestamps that have no explicit offset; "
        "unqualified timestamps remain null when omitted.",
    )
    parser.add_argument(
        "--raw-archive",
        type=Path,
        help="Optional JSONL path to preserve each original source record.",
    )
    args = parser.parse_args()
    with args.field_map.open(encoding="utf-8") as mapping_file:
        field_mapping = json.load(mapping_file)
    unknown_fields = set(field_mapping) - MAPPING_FIELDS
    if unknown_fields:
        parser.error(f"Field map contains unknown canonical fields: {sorted(unknown_fields)}")
    count = normalize_source(
        args.input,
        args.source_name,
        args.source_url,
        field_mapping,
        args.output,
        args.raw_archive,
        args.source_timezone,
    )
    print(json.dumps({"normalized_records": count, "output": str(args.output)}))


if __name__ == "__main__":
    main()
