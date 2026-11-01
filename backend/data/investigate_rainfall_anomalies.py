import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend/data/processed"

CONFIG = {
    "daily": {
        "file": "rainfall_daily_mumbai_region.csv",
        "rainfall": "Manual Daily Rainfall (mm)",
        "threshold": 200
    },
    "hourly": {
        "file": "rainfall_hourly_mumbai_region.csv",
        "rainfall": "Telemetry Hourly Rainfall (mm)",
        "threshold": 50
    }
}

for name, config in CONFIG.items():
    print("\n" + "=" * 75)
    print(name.upper(), "ANOMALY INVESTIGATION")
    print("=" * 75)

    df = pd.read_csv(DATA / config["file"])

    rainfall = config["rainfall"]

    df["Data Acquisition Time"] = pd.to_datetime(
        df["Data Acquisition Time"], errors="coerce"
    )

    df[rainfall] = pd.to_numeric(
        df[rainfall], errors="coerce"
    )

    # Extreme readings
    extreme = df[df[rainfall] > config["threshold"]].copy()

    print("\nExtreme records:", len(extreme))

    print(extreme[
        ["Station", "District", "Data Acquisition Time", rainfall]
    ].sort_values(rainfall, ascending=False).head(30).to_string(index=False))

    # Station-wise statistics
    station_stats = df.groupby("Station")[rainfall].agg(
        ["count", "mean", "median", "max"]
    ).sort_values("max", ascending=False)

    print("\nTop 15 stations by maximum rainfall:")
    print(station_stats.head(15).to_string())

    # Duplicate station/timestamp combinations
    duplicates = df[
        df.duplicated(
            subset=["Station", "Latitude", "Longitude",
                    "Data Acquisition Time"],
            keep=False
        )
    ]

    print("\nRepeated station/timestamp rows:", len(duplicates))

    if not duplicates.empty:
        print(duplicates[
            ["Station", "Data Acquisition Time", rainfall]
        ].head(20).to_string(index=False))

    # Save suspicious readings without deleting anything
    output = DATA / f"{name}_extreme_rainfall_review.csv"
    extreme.to_csv(output, index=False)

    print("\nSaved review:", output)
