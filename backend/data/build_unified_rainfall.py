import pandas as pd
from pathlib import Path

DATA = Path("backend/data/processed")

DAILY_FILE = DATA / "rainfall_daily_mumbai_region_qc.csv"
HOURLY_FILE = DATA / "rainfall_hourly_mumbai_region_qc.csv"

OUTPUT = DATA / "rainfall_unified_mumbai_region.csv"

def load_daily():
    df = pd.read_csv(DAILY_FILE)

    return pd.DataFrame({
        "station": df["Station"].astype(str).str.strip(),
        "district": df["District"].astype(str).str.strip(),
        "latitude": pd.to_numeric(df["Latitude"], errors="coerce"),
        "longitude": pd.to_numeric(df["Longitude"], errors="coerce"),
        "timestamp": pd.to_datetime(
            df["Data Acquisition Time"], errors="coerce"
        ),
        "rainfall_mm": pd.to_numeric(
            df["Manual Daily Rainfall (mm)"], errors="coerce"
        ),
        "temporal_resolution": "daily",
        "quality_flag": df["quality_flag"],
        "data_source": "Maharashtra SW"
    })

def load_hourly():
    df = pd.read_csv(HOURLY_FILE)

    return pd.DataFrame({
        "station": df["Station"].astype(str).str.strip(),
        "district": df["District"].astype(str).str.strip(),
        "latitude": pd.to_numeric(df["Latitude"], errors="coerce"),
        "longitude": pd.to_numeric(df["Longitude"], errors="coerce"),
        "timestamp": pd.to_datetime(
            df["Data Acquisition Time"], errors="coerce"
        ),
        "rainfall_mm": pd.to_numeric(
            df["Telemetry Hourly Rainfall (mm)"], errors="coerce"
        ),
        "temporal_resolution": "hourly",
        "quality_flag": df["quality_flag"],
        "data_source": "Maharashtra SW"
    })

daily = load_daily()
hourly = load_hourly()

unified = pd.concat([daily, hourly], ignore_index=True)

unified = unified.sort_values(
    ["timestamp", "station", "temporal_resolution"]
).reset_index(drop=True)

unified.to_csv(OUTPUT, index=False)

print("UNIFIED RAINFALL DATASET CREATED")
print("Total records:", len(unified))
print("Daily records:", (unified["temporal_resolution"] == "daily").sum())
print("Hourly records:", (unified["temporal_resolution"] == "hourly").sum())
print("Unique stations:", unified["station"].nunique())
print("Missing rainfall:", unified["rainfall_mm"].isna().sum())
print("\nQuality flags:")
print(unified["quality_flag"].value_counts())
print("\nDate range:")
print(unified["timestamp"].min(), "to", unified["timestamp"].max())
print("\nSaved:", OUTPUT)
