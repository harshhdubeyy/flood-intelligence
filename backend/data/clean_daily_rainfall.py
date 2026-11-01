import pandas as pd
from pathlib import Path

DATA = Path("backend/data/processed")

SOURCE = DATA / "rainfall_daily_mumbai_region.csv"
OUTPUT = DATA / "rainfall_daily_mumbai_region_qc.csv"

df = pd.read_csv(SOURCE)

timestamp = "Data Acquisition Time"
rainfall = "Manual Daily Rainfall (mm)"

df[timestamp] = pd.to_datetime(df[timestamp], errors="coerce")
df[rainfall] = pd.to_numeric(df[rainfall], errors="coerce")

before = len(df)

# Remove duplicate station/date records
df = df.drop_duplicates(
    subset=["Station", timestamp],
    keep="first"
).copy()

duplicates_removed = before - len(df)

# Assign quality flags
df["quality_flag"] = "normal"

df.loc[df[rainfall] > 200, "quality_flag"] = "extreme_review"

df.loc[df[rainfall] > 300, "quality_flag"] = "critical_review"

df.to_csv(OUTPUT, index=False)

print("Daily quality control complete")
print("Original rows:", before)
print("Duplicates removed:", duplicates_removed)
print("Final rows:", len(df))

print("\nQuality flag distribution:")
print(df["quality_flag"].value_counts())

print("\nSaved:", OUTPUT)