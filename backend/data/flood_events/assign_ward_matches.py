"""Use PostGIS and registered ward polygons to match coordinates without guessing."""

import argparse
import asyncio
import csv
import json
import math
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import get_settings
from backend.data.flood_events.schema import EVENT_FIELDS

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = DATA_DIR / "validated_events.csv"


def _float_or_none(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


async def assign_matches(input_path: Path, output_path: Path) -> int:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    count = 0
    try:
        with input_path.open(newline="", encoding="utf-8") as file:
            events = list(csv.DictReader(file))
        async with session_factory() as session:
            for event in events:
                latitude = _float_or_none(event.get("latitude"))
                longitude = _float_or_none(event.get("longitude"))
                issues = []
                if (
                    latitude is None
                    or longitude is None
                    or not -90 <= latitude <= 90
                    or not -180 <= longitude <= 180
                ):
                    if latitude is None or longitude is None:
                        issues.append("spatial_match_not_attempted_missing_coordinates")
                    else:
                        issues.append("spatial_match_not_attempted_invalid_coordinates")
                    event["spatial_ward_id"] = None
                    event["ward_match_method"] = "not_attempted_invalid_or_missing_coordinates"
                    try:
                        existing_issues = json.loads(event.get("validation_issues") or "[]")
                    except json.JSONDecodeError:
                        existing_issues = [event.get("validation_issues")]
                    if not isinstance(existing_issues, list):
                        existing_issues = [str(existing_issues)]
                    event["validation_issues"] = json.dumps(
                        sorted(set(existing_issues + issues))
                    )
                    count += 1
                    continue
                matches = (
                    await session.execute(
                        text(
                            """
                            SELECT ward_id
                            FROM wards
                            WHERE ST_Covers(
                                geom,
                                ST_SetSRID(ST_Point(:longitude, :latitude), 4326)
                            )
                            ORDER BY ward_id
                            """
                        ),
                        {"longitude": longitude, "latitude": latitude},
                    )
                ).scalars().all()
                source_ward = event.get("ward_id") or None
                if len(matches) == 1:
                    matched_ward = matches[0]
                    event["spatial_ward_id"] = matched_ward
                    if source_ward and source_ward != matched_ward:
                        issues.append(f"source_ward_mismatch:{source_ward}!={matched_ward}")
                        event["ward_match_method"] = "postgis_st_covers_source_ward_mismatch"
                    elif not source_ward:
                        event["ward_id"] = matched_ward
                        event["ward_match_method"] = "postgis_st_covers_coordinate_accuracy_unknown"
                    else:
                        event["ward_match_method"] = "postgis_st_covers_matches_source_ward"
                elif len(matches) > 1:
                    issues.append("coordinate_matches_multiple_wards")
                    event["ward_match_method"] = "ambiguous_postgis_boundary"
                else:
                    issues.append(
                        f"source_ward_coordinate_outside_registered_wards:{source_ward}"
                        if source_ward
                        else "coordinate_outside_registered_wards"
                    )
                    event["ward_match_method"] = "outside_registered_wards"
                if issues:
                    previous = event.get("validation_issues")
                    try:
                        existing_issues = json.loads(previous) if previous else []
                    except json.JSONDecodeError:
                        existing_issues = [previous]
                    event["validation_issues"] = json.dumps(existing_issues + issues)
                count += 1

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_fields = [*EVENT_FIELDS]
        if events and "duplicate_candidate" in events[0]:
            output_fields.append("duplicate_candidate")
        with output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=output_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(events)
    finally:
        await engine.dispose()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    count = asyncio.run(assign_matches(args.input, args.output))
    print(json.dumps({"events_checked": count, "output": str(args.output)}))


if __name__ == "__main__":
    main()
