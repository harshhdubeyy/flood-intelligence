import json
import pandas as pd

from pathlib import Path
from shapely.geometry import shape, Point
from shapely.ops import transform
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]

WARD_FILE = ROOT / "frontend/public/data/mumbai-wards.geojson"
RAW_DIR = ROOT / "backend/data/raw"
OUT_DIR = ROOT / "backend/data/processed"

OUT_DIR.mkdir(parents=True, exist_ok=True)

DATASETS = {
    "daily": {
        "file": "maharashtra_rainfall_daily.csv",
        "rainfall": "Manual Daily Rainfall (mm)"
    },
    "hourly": {
        "file": "maharashtra_rainfall_hourly.csv",
        "rainfall": "Telemetry Hourly Rainfall (mm)"
    }
}

# GeoJSON source coordinates are [latitude, longitude].
# Convert to standard geographic coordinates before geometry operations.
with open(WARD_FILE) as f:
    geojson = json.load(f)

wards = []

for feature in geojson["features"]:
    props = feature["properties"]
    geometry_data = feature["geometry"]

    def swap_coordinates(coords):
        if isinstance(coords[0], (int, float)):
            return [coords[1], coords[0]]
        return [swap_coordinates(c) for c in coords]

    geometry_data = {
        **geometry_data,
        "coordinates": swap_coordinates(geometry_data["coordinates"])
    }

    geometry = shape(geometry_data)

    # Project to UTM zone 43N for metric distance calculations.
    project = Transformer.from_crs(
        "EPSG:4326", "EPSG:32643", always_xy=True
    ).transform

    metric_geometry = transform(project, geometry)
    centroid = metric_geometry.centroid

    wards.append({
        "ward_name": str(props.get("NAME2") or props.get("Name", "")).strip(),
        "object_id": props.get("OBJECTID"),
        "geometry_type": geometry.geom_type,
        "centroid_lat": Transformer.from_crs(
            "EPSG:32643", "EPSG:4326", always_xy=True
        ).transform(centroid.x, centroid.y)[1],
        "centroid_lon": Transformer.from_crs(
            "EPSG:32643", "EPSG:4326", always_xy=True
        ).transform(centroid.x, centroid.y)[0],
        "area_sq_m": round(metric_geometry.area, 2),
        "perimeter_m": round(metric_geometry.length, 2),
        "geometry": metric_geometry
    })

coverage_rows = []
station_rows = []

for dataset_name, config in DATASETS.items():
    path = RAW_DIR / config["file"]
    df = pd.read_csv(path, low_memory=False)

    df["Data Acquisition Time"] = pd.to_datetime(
        df["Data Acquisition Time"],
        format="%d-%m-%Y %H:%M",
        errors="coerce"
    )

    station_groups = df.groupby(
        ["Station", "District", "Latitude", "Longitude"],
        dropna=False
    )

    stations = station_groups.agg(
        records=(config["rainfall"], "count"),
        first_record=("Data Acquisition Time", "min"),
        last_record=("Data Acquisition Time", "max")
    ).reset_index()

    project = Transformer.from_crs(
        "EPSG:4326", "EPSG:32643", always_xy=True
    ).transform

    for _, station in stations.iterrows():
        point = transform(
            project,
            Point(float(station["Longitude"]), float(station["Latitude"]))
        )

        station_rows.append({
            "dataset": dataset_name,
            "station": station["Station"],
            "district": station["District"],
            "latitude": station["Latitude"],
            "longitude": station["Longitude"],
            "records": station["records"],
            "first_record": station["first_record"],
            "last_record": station["last_record"]
        })

        for ward in wards:
            polygon = ward["geometry"]
            distance = point.distance(polygon)

            coverage_rows.append({
                "dataset": dataset_name,
                "ward_name": ward["ward_name"],
                "object_id": ward["object_id"],
                "station": station["Station"],
                "district": station["District"],
                "station_lat": station["Latitude"],
                "station_lon": station["Longitude"],
                "distance_to_ward_km": round(distance / 1000, 3),
                "inside_ward": polygon.covers(point),
                "records": station["records"],
                "first_record": station["first_record"],
                "last_record": station["last_record"]
            })

coverage = pd.DataFrame(coverage_rows)
stations_df = pd.DataFrame(station_rows)

coverage.to_csv(OUT_DIR / "ward_station_distances.csv", index=False)
stations_df.to_csv(OUT_DIR / "rainfall_stations.csv", index=False)

# One nearest station per ward and dataset.
nearest = (
    coverage.sort_values("distance_to_ward_km")
    .groupby(["dataset", "ward_name"], as_index=False)
    .first()
)

nearest.to_csv(OUT_DIR / "ward_rainfall_coverage.csv", index=False)

print("\nWARD COVERAGE SUMMARY")
print("=" * 65)

for dataset in DATASETS:
    subset = nearest[nearest["dataset"] == dataset]

    print(f"\n{dataset.upper()}")
    print("Wards:", len(subset))
    print("Within 5 km:", (subset["distance_to_ward_km"] <= 5).sum())
    print("Within 10 km:", (subset["distance_to_ward_km"] <= 10).sum())
    print("Within 25 km:", (subset["distance_to_ward_km"] <= 25).sum())
    print("Inside a ward:", subset["inside_ward"].sum())

print("\nNEAREST STATION PER WARD")
print(
    nearest[
        ["dataset", "ward_name", "station",
         "distance_to_ward_km", "records"]
    ].to_string(index=False)
)

print("\nGenerated:")
print(OUT_DIR / "rainfall_stations.csv")
print(OUT_DIR / "ward_station_distances.csv")
print(OUT_DIR / "ward_rainfall_coverage.csv")
