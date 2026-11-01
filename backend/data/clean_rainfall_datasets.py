import json
import pandas as pd

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "backend/data/raw"
PROCESSED = ROOT / "backend/data/processed"
METADATA = ROOT / "backend/data/metadata"

PROCESSED.mkdir(parents=True, exist_ok=True)
METADATA.mkdir(parents=True, exist_ok=True)

CONFIG = {
    "daily": {
        "file": "maharashtra_rainfall_daily.csv",
        "rainfall": "Manual Daily Rainfall (mm)",
        "output": "rainfall_daily_clean.csv",
        "regional_output": "rainfall_daily_mumbai_region.csv"
    },
    "hourly": {
        "file": "maharashtra_rainfall_hourly.csv",
        "rainfall": "Telemetry Hourly Rainfall (mm)",
        "output": "rainfall_hourly_clean.csv",
        "regional_output": "rainfall_hourly_mumbai_region.csv"
    }
}

MAX_DISTANCE_KM = 75

coverage = pd.read_csv(
    PROCESSED / "ward_station_distances.csv"
)

quality_report = {
    "source": "Maharashtra Surface Water Department",
    "regional_filter_distance_km": MAX_DISTANCE_KM,
    "datasets": {}
}

for dataset, config in CONFIG.items():
    print(f"\nProcessing {dataset} rainfall...")

    df = pd.read_csv(
        RAW / config["file"],
        low_memory=False
    )

    original_rows = len(df)

    # Normalize column names and text fields.
    df.columns = df.columns.str.strip()

    text_columns = df.select_dtypes(
        include=["object"]
    ).columns

    for col in text_columns:
        df[col] = df[col].str.strip()

    # Parse timestamps.
    df["Data Acquisition Time"] = pd.to_datetime(
        df["Data Acquisition Time"],
        format="%d-%m-%Y %H:%M",
        errors="coerce"
    )

    # Convert measurements and coordinates to numeric.
    rainfall_col = config["rainfall"]

    for col in [rainfall_col, "Latitude", "Longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    invalid_timestamps = int(
        df["Data Acquisition Time"].isna().sum()
    )

    original_missing_rainfall = int(
        df[rainfall_col].isna().sum()
    )

    negative_rainfall = int(
        (df[rainfall_col] < 0).sum()
    )

    invalid_coordinates = int(
        (
            df["Latitude"].isna()
            | df["Longitude"].isna()
            | ~df["Latitude"].between(-90, 90)
            | ~df["Longitude"].between(-180, 180)
        ).sum()
    )

    # Negative rainfall values are invalid measurements.
    df.loc[df[rainfall_col] < 0, rainfall_col] = pd.NA
    missing_rainfall_after_cleaning = int(
    df[rainfall_col].isna().sum()
    )

    # Remove exact duplicate rows only.
    exact_duplicates = int(df.duplicated().sum())
    df = df.drop_duplicates().copy()

    # Keep rows even when rainfall or timestamps are missing.
    df["data_source"] = "Maharashtra Surface Water Department"
    df["temporal_resolution"] = dataset
    df["rainfall_unit"] = "mm"

    # Save the full cleaned Maharashtra dataset.
    full_output = PROCESSED / config["output"]
    df.to_csv(full_output, index=False)

    # Identify stations within 75 km of at least one BMC ward.
    relevant = coverage[
        (coverage["dataset"] == dataset)
        & (coverage["distance_to_ward_km"] <= MAX_DISTANCE_KM)
    ][
        ["station", "district", "station_lat", "station_lon"]
    ].drop_duplicates()

    relevant = relevant.rename(columns={
        "station": "Station",
        "district": "District",
        "station_lat": "Latitude",
        "station_lon": "Longitude"
    })

    regional = df.merge(
        relevant,
        on=["Station", "District", "Latitude", "Longitude"],
        how="inner"
    )

    regional_output = PROCESSED / config["regional_output"]
    regional.to_csv(regional_output, index=False)

    # Count repeated station/timestamp combinations.
    repeated_station_times = int(
        regional.duplicated(
            subset=["Station", "Latitude", "Longitude",
                    "Data Acquisition Time"]
        ).sum()
    )

    report = {
        "source_file": config["file"],
        "clean_file": config["output"],
        "regional_file": config["regional_output"],
        "original_rows": original_rows,
        "cleaned_rows": len(df),
        "regional_rows": len(regional),
        "regional_unique_stations": int(
            regional["Station"].nunique()
        ),
        "invalid_timestamps": invalid_timestamps,
        "missing_rainfall_values_before_cleaning": original_missing_rainfall,
        "missing_rainfall_values_after_cleaning": missing_rainfall_after_cleaning,
        "negative_rainfall_values": negative_rainfall,
        "invalid_coordinates": invalid_coordinates,
        "exact_duplicate_rows_removed": exact_duplicates,
        "repeated_station_timestamp_rows_in_regional_data": (
            repeated_station_times
        ),
        "first_timestamp": (
            df["Data Acquisition Time"].min().isoformat()
            if df["Data Acquisition Time"].notna().any()
            else None
        ),
        "last_timestamp": (
            df["Data Acquisition Time"].max().isoformat()
            if df["Data Acquisition Time"].notna().any()
            else None
        )
    }

    quality_report["datasets"][dataset] = report

    print(f"Original rows: {original_rows}")
    print(f"Cleaned rows: {len(df)}")
    print(f"Regional rows: {len(regional)}")
    print(f"Regional stations: {regional['Station'].nunique()}")
    print(f"Invalid timestamps: {invalid_timestamps}")
    print(f"Missing rainfall: {original_missing_rainfall}")
    print(f"Negative rainfall: {negative_rainfall}")
    print(f"Exact duplicates removed: {exact_duplicates}")

report_path = METADATA / "rainfall_quality_report.json"

with open(report_path, "w") as f:
    json.dump(quality_report, f, indent=4, default=str)

print("\nRainfall dataset processing complete.")
print("Quality report:", report_path)
