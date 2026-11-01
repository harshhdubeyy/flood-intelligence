import pandas as pd
import numpy as np
import json

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend/data/processed"
OUTPUT = ROOT / "backend/data/metadata"

CONFIG = {
    "daily": {
        "file": "rainfall_daily_mumbai_region.csv",
        "rainfall": "Manual Daily Rainfall (mm)"
    },
    "hourly": {
        "file": "rainfall_hourly_mumbai_region.csv",
        "rainfall": "Telemetry Hourly Rainfall (mm)"
    }
}

report = {}

for name, config in CONFIG.items():
    print("\n" + "=" * 65)
    print(name.upper(), "RAINFALL VALIDATION")
    print("=" * 65)

    df = pd.read_csv(DATA / config["file"])
    rainfall = config["rainfall"]

    df["Data Acquisition Time"] = pd.to_datetime(
        df["Data Acquisition Time"], errors="coerce"
    )

    values = pd.to_numeric(df[rainfall], errors="coerce")
    valid = values.dropna()

    stats = {
        "total_records": len(df),
        "unique_stations": int(df["Station"].nunique()),
        "missing_rainfall": int(values.isna().sum()),
        "negative_rainfall": int((values < 0).sum()),
        "zero_rainfall_records": int((values == 0).sum()),
        "positive_rainfall_records": int((values > 0).sum()),
        "mean_mm": round(float(valid.mean()), 3) if len(valid) else None,
        "median_mm": round(float(valid.median()), 3) if len(valid) else None,
        "p95_mm": round(float(valid.quantile(.95)), 3) if len(valid) else None,
        "p99_mm": round(float(valid.quantile(.99)), 3) if len(valid) else None,
        "maximum_mm": round(float(valid.max()), 3) if len(valid) else None,
        "first_timestamp": str(df["Data Acquisition Time"].min()),
        "last_timestamp": str(df["Data Acquisition Time"].max())
    }

    print("\nOverall statistics:")
    for key, value in stats.items():
        print(f"{key}: {value}")

    # Station-wise record coverage.
    station_stats = df.groupby("Station").agg(
        records=(rainfall, "count"),
        first_record=("Data Acquisition Time", "min"),
        last_record=("Data Acquisition Time", "max"),
        mean_rainfall=(rainfall, "mean"),
        maximum_rainfall=(rainfall, "max")
    ).reset_index()

    station_stats.to_csv(
        DATA / f"{name}_station_quality.csv", index=False
    )

    print("\nStations with fewest valid records:")
    print(station_stats.sort_values("records").head(10).to_string(index=False))

    # Temporal gaps: report observed intervals, not assumed missing hours.
    if name == "hourly":
        df = df.sort_values(["Station", "Data Acquisition Time"])
        df["previous_time"] = df.groupby("Station")[
            "Data Acquisition Time"
        ].shift(1)

        df["gap_hours"] = (
            df["Data Acquisition Time"] - df["previous_time"]
        ).dt.total_seconds() / 3600

        gaps = df["gap_hours"].dropna()

        stats["intervals_over_1h"] = int((gaps > 1).sum())
        stats["intervals_over_6h"] = int((gaps > 6).sum())
        stats["intervals_over_24h"] = int((gaps > 24).sum())

        print("\nHourly timestamp gaps:")
        print("Intervals > 1 hour:", stats["intervals_over_1h"])
        print("Intervals > 6 hours:", stats["intervals_over_6h"])
        print("Intervals > 24 hours:", stats["intervals_over_24h"])

    # Seasonal distribution.
    df["month"] = df["Data Acquisition Time"].dt.month

    monthly = (
        df.groupby("month")[rainfall]
        .agg(["count", "mean", "max"])
        .round(3)
    )

    print("\nMonthly rainfall distribution:")
    print(monthly.to_string())

    monthly.to_csv(DATA / f"{name}_monthly_quality.csv")

    report[name] = stats

with open(OUTPUT / "rainfall_validation_report.json", "w") as f:
    json.dump(report, f, indent=4)

print("\nValidation completed.")
print("Reports saved in:", OUTPUT)
