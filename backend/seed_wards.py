"""Idempotently register Mumbai wards from the authoritative frontend GeoJSON."""

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from geoalchemy2.elements import WKTElement
from pyproj import Transformer
from shapely.geometry import MultiPolygon, shape
from shapely.ops import transform
from sqlalchemy import select

from backend.models.database import async_session_factory
from backend.models.ward import Ward

ROOT = Path(__file__).resolve().parents[1]
WARD_GEOJSON = ROOT / "frontend/public/data/mumbai-wards.geojson"
AREA_TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)


def _ward_code(value: Any) -> str:
    code = str(value or "").strip().upper()
    if not code:
        raise ValueError("Ward GeoJSON feature is missing a ward code.")
    return code


def _normalized_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"^(?:MH[-_]*)?BMC[-_]*", "", value.upper()))


def _swap_geojson_coordinates(coordinates: list[Any]) -> list[Any]:
    if coordinates and isinstance(coordinates[0], (int, float)):
        if len(coordinates) < 2:
            raise ValueError("Ward GeoJSON contains an incomplete coordinate.")
        return [coordinates[1], coordinates[0]]
    return [_swap_geojson_coordinates(coordinate) for coordinate in coordinates]


def _feature_geometry(feature: dict[str, Any]) -> tuple[str, str, float]:
    properties = feature.get("properties") or {}
    source_code = _ward_code(properties.get("NAME2") or properties.get("Name"))
    raw_geometry = feature.get("geometry")
    if not isinstance(raw_geometry, dict):
        raise ValueError(f"Ward {source_code} has no geometry.")

    swapped_geometry = {
        **raw_geometry,
        "coordinates": _swap_geojson_coordinates(raw_geometry.get("coordinates", [])),
    }
    geometry = shape(swapped_geometry)
    if geometry.geom_type == "Polygon":
        geometry = MultiPolygon([geometry])
    if geometry.geom_type != "MultiPolygon" or geometry.is_empty or not geometry.is_valid:
        raise ValueError(f"Ward {source_code} geometry is invalid or unsupported.")

    west, south, east, north = geometry.bounds
    if not (72.0 <= west <= east <= 73.2 and 18.5 <= south <= north <= 20.0):
        raise ValueError(
            f"Ward {source_code} coordinates are outside the expected Mumbai longitude/latitude bounds."
        )

    metric_geometry = transform(AREA_TRANSFORMER.transform, geometry)
    if not metric_geometry.is_valid or metric_geometry.area <= 0:
        raise ValueError(f"Ward {source_code} has invalid projected geometry.")

    return source_code, geometry.wkt, round(metric_geometry.area / 1_000_000, 4)


def _load_features() -> list[tuple[str, str, float]]:
    with WARD_GEOJSON.open(encoding="utf-8") as file:
        geojson = json.load(file)
    if geojson.get("type") != "FeatureCollection":
        raise ValueError("Mumbai ward boundary file is not a GeoJSON FeatureCollection.")

    features = [_feature_geometry(feature) for feature in geojson.get("features", [])]
    normalized_codes = [_normalized_code(code) for code, _, _ in features]
    if len(features) != 24 or len(set(normalized_codes)) != 24:
        raise ValueError(
            f"Expected 24 unique ward features; found {len(features)} features and "
            f"{len(set(normalized_codes))} unique identifiers."
        )
    return features


async def seed_wards() -> dict[str, int]:
    """Insert missing wards and correct source geometry without overwriting existing metadata."""
    features = _load_features()
    inserted = 0
    geometry_updated = 0

    async with async_session_factory() as session:
        existing_rows = (await session.execute(select(Ward))).scalars().all()
        existing_by_code: dict[str, Ward] = {}
        for ward in existing_rows:
            normalized = _normalized_code(ward.ward_id)
            if normalized in existing_by_code:
                raise ValueError(f"Existing ward identifiers collide after normalization: {ward.ward_id}")
            existing_by_code[normalized] = ward

        for source_code, geometry_wkt, area_sqkm in features:
            normalized = _normalized_code(source_code)
            existing = existing_by_code.get(normalized)
            if existing is not None:
                existing.geom = WKTElement(geometry_wkt, srid=4326)
                geometry_updated += 1
                continue

            ward_id = f"BMC-{normalized}"
            session.add(
                Ward(
                    ward_id=ward_id,
                    ward_name=source_code,
                    city="Mumbai",
                    geom=WKTElement(geometry_wkt, srid=4326),
                    area_sqkm=area_sqkm,
                    population=None,
                    is_coastal=None,
                    avg_elevation_m=None,
                    drainage_index=None,
                )
            )
            inserted += 1

        await session.commit()

        rows = (await session.execute(select(Ward))).scalars().all()
        registered_codes = {_normalized_code(ward.ward_id) for ward in rows}
        expected_codes = {_normalized_code(code) for code, _, _ in features}
        if registered_codes != expected_codes or len(rows) != 24:
            raise RuntimeError(
                f"Ward registration verification failed: {len(rows)} rows, "
                f"{len(registered_codes)} normalized IDs."
            )

    result = {"registered": len(features), "inserted": inserted, "geometry_updated": geometry_updated}
    print(json.dumps(result, sort_keys=True))
    return result


if __name__ == "__main__":
    asyncio.run(seed_wards())
