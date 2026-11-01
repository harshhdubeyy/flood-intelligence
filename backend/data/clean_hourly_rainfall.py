import pandas as pd
from pathlib import Path

DATA = Path("backend/data/processed")

SOURCE = DATA / "rainfall_hourly_mumbai_region.csv"
OUTPUT = DATA / "rainfall_hourly_mumbai_region_qc.csv"

df = pd.read_csv(SOURCE)

timestamp = "Data Acquisition Time"
rainfall = "Telemetry Hourly Rainfall (mm)"

df[timestamp] = pd.to_datetime(df[timestamp], errors="coerce")
df[rainfall] = pd.to_numeric(df[rainfall], errors="coerce")

# Remove exact duplicate station/timestamp records.
before = len(df)

df = df.drop_duplicates(
    subset=["Station", timestamp],
    keep="first"
).copy()

duplicates_removed = before - len(df)

# Add quality flags without deleting extreme readings.
df["quality_flag"] = "normal"

df.loc[df[rainfall] > 50, "quality_flag"] = "extreme_review"

# Flag exceptionally high readings for manual verification.
df.loc[df[rainfall] > 200, "quality_flag"] = "critical_review"

# Flag suspicious Dhamni readings during July 25–26, 2022.
dhamni_event = (
    df["Station"].str.strip().str.lower().eq("dhamni")
    & df[timestamp].between(
        "2022-07-25 00:00:00",
        "2022-07-26 23:59:59"
    )
)

df.loc[dhamni_event, "quality_flag"] = "station_event_review"

df.to_csv(OUTPUT, index=False)

print("Hourly quality control complete")
print("Original rows:", before)
print("Duplicates removed:", duplicates_removed)
print("Final rows:", len(df))

print("\nQuality flag distribution:")
print(df["quality_flag"].value_counts())

print("\nSaved:", OUTPUT)