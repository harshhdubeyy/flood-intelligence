"""Align verified event records with past station rainfall without editing source data."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import get_settings
from backend.data.flood_events.schema import EVIDENCE_CATEGORIES

DATA_DIR = Path(__file__).resolve().parent
PROJECT_DATA_DIR = DATA_DIR.parent
DEFAULT_EVENTS = DATA_DIR / "validated_events.csv"
DEFAULT_HOURLY = PROJECT_DATA_DIR / "processed/rainfall_hourly_mumbai_region_qc.csv"
DEFAULT_DAILY = PROJECT_DATA_DIR / "processed/rainfall_daily_mumbai_region_qc.csv"
DEFAULT_OUTPUT = DATA_DIR / "rainfall_aligned_events.csv"
DEFAULT_REPORT = DATA_DIR / "rainfall_alignment_report.json"
VERIFIED_CATEGORIES = {
    "operator_confirmed_citizen",
    "independently_verified_historical",
    "officially_confirmed_historical",
}
WINDOWS = {
    "1h": (timedelta(hours=1), "hourly", 1),
    "3h": (timedelta(hours=3), "hourly", 3),
    "6h": (timedelta(hours=6), "hourly", 6),
    "12h": (timedelta(hours=12), "hourly", 12),
    "24h": (timedelta(hours=24), "hourly", 24),
    "3d": (timedelta(days=3), "daily", 3),
    "7d": (timedelta(days=7), "daily", 7),
}
OUTPUT_FIELDS = (
    "event_id",
    "evidence_category",
    "event_timestamp",
    "source_name",
    "ward_id",
    "latitude",
    "longitude",
    "rainfall_timezone",
    "hourly_station_id",
    "hourly_station_distance_km",
    "daily_station_id",
    "daily_station_distance_km",
    "station_distance_basis",
    *(
        field
        for horizon in WINDOWS
        for field in (
            f"rainfall_{horizon}_mm",
            f"rainfall_{horizon}_observed_sum_mm",
            f"rainfall_{horizon}_observation_count",
            f"rainfall_{horizon}_expected_observation_count",
            f"rainfall_{horizon}_coverage_status",
            f"rainfall_{horizon}_window_start",
            f"rainfall_{horizon}_window_end",
        )
    ),
)


@dataclass
class Station:
    station_id: str
    latitude: float
    longitude: float
    observations: dict[datetime, list[float]] = field(default_factory=lambda: defaultdict(list))
    sample_times: Counter[tuple[int, int]] = field(default_factory=Counter)

    @property
    def daily_sample_time(self) -> tuple[int, int] | None:
        if not self.sample_times:
            return None
        most_common = self.sample_times.most_common()
        if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
            return None
        return most_common[0][0]


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_rainfall_timestamp(value: str, zone: ZoneInfo) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def _read_stations(
    path: Path,
    zone: ZoneInfo,
    value_column: str,
) -> tuple[dict[str, Station], dict[str, int]]:
    stations: dict[str, Station] = {}
    rejected = Counter()
    with path.open(newline="", encoding="utf-8-sig") as file:
        for row_number, row in enumerate(csv.DictReader(file), start=2):
            station_name = (row.get("Station") or "").strip()
            latitude = _float(row.get("Latitude"))
            longitude = _float(row.get("Longitude"))
            timestamp = _parse_rainfall_timestamp(row.get("Data Acquisition Time") or "", zone)
            rainfall = _float(row.get(value_column))
            quality_flag = (row.get("quality_flag") or "").strip().lower()
            if not station_name:
                rejected["missing_station_id"] += 1
                continue
            if latitude is None or longitude is None or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                rejected["invalid_station_coordinates"] += 1
                continue
            if timestamp is None:
                rejected["invalid_station_timestamp"] += 1
                continue
            if rainfall is None or rainfall < 0:
                rejected["missing_or_negative_rainfall"] += 1
                continue
            if quality_flag and quality_flag != "normal":
                rejected["non_normal_quality_flag"] += 1
                continue
            station_id = f"{station_name}|{latitude:.6f}|{longitude:.6f}"
            station = stations.setdefault(
                station_id,
                Station(station_id, latitude, longitude),
            )
            station.observations[timestamp].append(rainfall)
            station.sample_times[(timestamp.hour, timestamp.minute)] += 1
    rejected["records_loaded"] = sum(
        len(values) for station in stations.values() for values in station.observations.values()
    )
    return stations, dict(rejected)


def _distance_km(latitude: float, longitude: float, station: Station) -> float:
    lat1, lat2 = math.radians(latitude), math.radians(station.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(station.longitude - longitude)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def _nearest_station(
    stations: dict[str, Station],
    latitude: float | None,
    longitude: float | None,
) -> tuple[Station | None, float | None]:
    if latitude is None or longitude is None:
        return None, None
    choices = (
        (_distance_km(latitude, longitude, station), station)
        for station in stations.values()
    )
    distance, station = min(choices, key=lambda pair: pair[0], default=(None, None))
    return station, distance


async def _ward_centroids() -> dict[str, tuple[float, float]]:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT ward_id, ST_Y(ST_Centroid(geom)) AS latitude,
                               ST_X(ST_Centroid(geom)) AS longitude
                        FROM wards
                        WHERE geom IS NOT NULL AND ST_IsValid(geom)
                        """
                    )
                )
            ).all()
            return {
                row.ward_id: (float(row.latitude), float(row.longitude))
                for row in rows
            }
    finally:
        await engine.dispose()


def _window_values(
    station: Station | None,
    event_time: datetime,
    horizon: str,
    duration: timedelta,
    resolution: str,
    expected_count: int,
) -> dict[str, Any]:
    prefix = f"rainfall_{horizon}"
    start = event_time - duration
    result: dict[str, Any] = {
        f"{prefix}_mm": None,
        f"{prefix}_observed_sum_mm": None,
        f"{prefix}_observation_count": 0,
        f"{prefix}_expected_observation_count": expected_count,
        f"{prefix}_coverage_status": "no_nearby_station" if station is None else "no_observations",
        f"{prefix}_window_start": start.isoformat(),
        f"{prefix}_window_end": event_time.isoformat(),
    }
    if station is None:
        return result

    in_window = {
        timestamp: values
        for timestamp, values in station.observations.items()
        if start < timestamp <= event_time
    }
    observation_count = sum(len(values) for values in in_window.values())
    observed_sum = sum(value for values in in_window.values() for value in values)
    result[f"{prefix}_observation_count"] = observation_count
    result[f"{prefix}_observed_sum_mm"] = observed_sum if observation_count else None

    if resolution == "hourly":
        expected_slots: list[datetime] = []
        cursor = event_time.replace(minute=0, second=0, microsecond=0)
        while cursor > start and cursor <= event_time:
            expected_slots.append(cursor)
            cursor -= timedelta(hours=1)
        slot_values = [station.observations.get(slot, []) for slot in expected_slots]
        if any(len(values) > 1 for values in slot_values) or any(
            len(values) > 1 for values in in_window.values()
        ):
            result[f"{prefix}_coverage_status"] = "duplicate_timestamp_review"
        elif len(expected_slots) == expected_count and all(slot_values):
            result[f"{prefix}_mm"] = sum(values[0] for values in slot_values)
            result[f"{prefix}_coverage_status"] = "complete"
        else:
            result[f"{prefix}_coverage_status"] = "incomplete_missing_observations"
        return result

    sample_time = station.daily_sample_time
    if sample_time is None:
        result[f"{prefix}_coverage_status"] = "daily_sampling_schedule_ambiguous"
        return result
    local_event = event_time
    slot = local_event.replace(
        hour=sample_time[0],
        minute=sample_time[1],
        second=0,
        microsecond=0,
    )
    if slot > local_event:
        slot -= timedelta(days=1)
    expected_slots = [slot - timedelta(days=day) for day in range(expected_count)]
    slot_values = [station.observations.get(expected, []) for expected in expected_slots]
    if any(len(values) > 1 for values in slot_values) or any(
        len(values) > 1 for values in in_window.values()
    ):
        result[f"{prefix}_coverage_status"] = "duplicate_timestamp_review"
    elif all(slot_values) and all(start < expected <= event_time for expected in expected_slots):
        result[f"{prefix}_mm"] = sum(values[0] for values in slot_values)
        result[f"{prefix}_coverage_status"] = "complete"
    else:
        result[f"{prefix}_coverage_status"] = "incomplete_missing_observations"
    return result


def align_event(
    event: dict[str, str],
    hourly_stations: dict[str, Station],
    daily_stations: dict[str, Station],
    rainfall_timezone: str,
    ward_centroids: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    zone = ZoneInfo(rainfall_timezone)
    event_timestamp = datetime.fromisoformat(event["event_timestamp"].replace("Z", "+00:00"))
    if event_timestamp.tzinfo is None:
        raise ValueError(f"Event {event.get('event_id')} timestamp has no timezone.")
    event_time = event_timestamp.astimezone(zone)
    latitude = _float(event.get("latitude"))
    longitude = _float(event.get("longitude"))
    if latitude is not None and not -90 <= latitude <= 90:
        latitude = None
    if longitude is not None and not -180 <= longitude <= 180:
        longitude = None
    if latitude is None or longitude is None:
        latitude = longitude = None
    ward_id = event.get("spatial_ward_id") or event.get("ward_id")
    distance_basis = "event_coordinates"
    station_latitude, station_longitude = latitude, longitude
    if (
        station_latitude is None
        and station_longitude is None
        and ward_centroids
        and ward_id in ward_centroids
    ):
        station_latitude, station_longitude = ward_centroids[ward_id]
        distance_basis = "registered_ward_centroid"

    hourly_station, hourly_distance = _nearest_station(
        hourly_stations,
        station_latitude,
        station_longitude,
    )
    daily_station, daily_distance = _nearest_station(
        daily_stations,
        station_latitude,
        station_longitude,
    )
    aligned: dict[str, Any] = {
        "event_id": event.get("event_id"),
        "evidence_category": event.get("evidence_category"),
        "event_timestamp": event_time.isoformat(),
        "source_name": event.get("source_name"),
        "ward_id": ward_id,
        "latitude": latitude,
        "longitude": longitude,
        "rainfall_timezone": rainfall_timezone,
        "hourly_station_id": hourly_station.station_id if hourly_station else None,
        "hourly_station_distance_km": round(hourly_distance, 3) if hourly_distance is not None else None,
        "daily_station_id": daily_station.station_id if daily_station else None,
        "daily_station_distance_km": round(daily_distance, 3) if daily_distance is not None else None,
        "station_distance_basis": distance_basis if station_latitude is not None else "no_event_coordinates_or_ward_centroid",
    }
    for horizon, (duration, resolution, expected_count) in WINDOWS.items():
        station = hourly_station if resolution == "hourly" else daily_station
        aligned.update(
            _window_values(
                station,
                event_time,
                horizon,
                duration,
                resolution,
                expected_count,
            )
        )
    return aligned


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def align_events(
    events_path: Path,
    hourly_path: Path,
    daily_path: Path,
    output_path: Path,
    report_path: Path,
    rainfall_timezone: str,
) -> dict[str, Any]:
    zone = ZoneInfo(rainfall_timezone)
    with events_path.open(newline="", encoding="utf-8-sig") as file:
        source_events = list(csv.DictReader(file))
    verified_events = []
    excluded_reasons = Counter()
    for event in source_events:
        if event.get("evidence_category") not in VERIFIED_CATEGORIES:
            excluded_reasons["not_explicitly_verified"] += 1
            continue
        try:
            timestamp = datetime.fromisoformat(
                (event.get("event_timestamp") or "").replace("Z", "+00:00")
            )
        except ValueError:
            excluded_reasons["missing_or_invalid_event_timestamp"] += 1
            continue
        if timestamp.tzinfo is None:
            excluded_reasons["event_timestamp_missing_timezone"] += 1
            continue
        verified_events.append(event)
    hourly_stations, hourly_rejected = _read_stations(
        hourly_path,
        zone,
        "Telemetry Hourly Rainfall (mm)",
    )
    daily_stations, daily_rejected = _read_stations(
        daily_path,
        zone,
        "Manual Daily Rainfall (mm)",
    )

    ward_centroids = {}
    if any(
        (_float(event.get("latitude")) is None or _float(event.get("longitude")) is None)
        and (event.get("ward_id") or event.get("spatial_ward_id"))
        for event in verified_events
    ):
        ward_centroids = asyncio.run(_ward_centroids())
    aligned_events = [
        align_event(
            event,
            hourly_stations,
            daily_stations,
            rainfall_timezone,
            ward_centroids,
        )
        for event in verified_events
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(aligned_events)

    complete_counts = {
        horizon: sum(
            event.get(f"rainfall_{horizon}_coverage_status") == "complete"
            for event in aligned_events
        )
        for horizon in WINDOWS
    }
    coverage_counts = {
        horizon: dict(
            Counter(
                event.get(f"rainfall_{horizon}_coverage_status", "unknown")
                for event in aligned_events
            )
        )
        for horizon in WINDOWS
    }
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rainfall_timezone": rainfall_timezone,
        "timezone_note": (
            "Naive rainfall timestamps were interpreted in the explicitly supplied IANA "
            "timezone. Confirm this timezone against the source provider's documentation."
        ),
        "input_sha256": {
            "events": _sha256(events_path),
            "hourly_rainfall": _sha256(hourly_path),
            "daily_rainfall": _sha256(daily_path),
        },
        "rainfall_source_files_modified": False,
        "source_event_record_count": len(source_events),
        "eligible_verified_event_count": len(verified_events),
        "excluded_event_count": len(source_events) - len(verified_events),
        "excluded_event_reasons": dict(excluded_reasons),
        "evidence_category_counts": dict(
            Counter(event.get("evidence_category") or "unknown" for event in source_events)
        ),
        "aligned_event_count": len(aligned_events),
        "hourly_station_count": len(hourly_stations),
        "daily_station_count": len(daily_stations),
        "hourly_observation_quality": hourly_rejected,
        "daily_observation_quality": daily_rejected,
        "complete_coverage_by_window": complete_counts,
        "coverage_status_by_window": coverage_counts,
        "method": {
            "station_selection": "nearest valid rainfall station by haversine distance to event coordinates or registered PostGIS ward centroid; basis is recorded per event",
            "hourly_windows": "sum exact hourly timestamps in (event_time - window, event_time]; no interpolation",
            "daily_windows": "sum exact daily schedule timestamps in (event_time - window, event_time]; schedule inferred from station's modal acquisition time",
            "missing_observations": "retained as null totals and labeled incomplete; no missing reading is treated as zero",
            "temporal_leakage": "observations after the event timestamp are excluded",
            "stationless_events": "retained in output with null rainfall and no_nearby_station status",
        },
        "output_csv": str(output_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--hourly", type=Path, default=DEFAULT_HOURLY)
    parser.add_argument("--daily", type=Path, default=DEFAULT_DAILY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--rainfall-timezone",
        required=True,
        help="IANA timezone declared by the rainfall data custodian for naive timestamps.",
    )
    args = parser.parse_args()
    report = align_events(
        args.events,
        args.hourly,
        args.daily,
        args.output,
        args.report,
        args.rainfall_timezone,
    )
    print(json.dumps({
        "source_event_record_count": report["source_event_record_count"],
        "eligible_verified_event_count": report["eligible_verified_event_count"],
        "aligned_event_count": report["aligned_event_count"],
        "complete_coverage_by_window": report["complete_coverage_by_window"],
    }, indent=2))


if __name__ == "__main__":
    main()
