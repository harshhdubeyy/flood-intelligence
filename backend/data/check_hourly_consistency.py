import pandas as pd
from pathlib import Path

DATA = Path("backend/data/processed")

df = pd.read_csv(DATA / "rainfall_hourly_mumbai_region.csv")

rainfall = "Telemetry Hourly Rainfall (mm)"
timestamp = "Data Acquisition Time"

df[timestamp] = pd.to_datetime(df[timestamp], errors="coerce")

# 1. Duplicate station/timestamp groups
grouped = (
    df.groupby(["Station", timestamp])[rainfall]
    .agg(["count", "nunique", "min", "max"])
    .reset_index()
)

duplicates = grouped[grouped["count"] > 1]

print("\nDUPLICATE ANALYSIS")
print("Duplicate groups:", len(duplicates))
print("Groups with conflicting rainfall:", 
      (duplicates["nunique"] > 1).sum())
print("Rows involved:", duplicates["count"].sum())

# 2. Inspect Dhamni extreme readings
print("\nDHAMNI: JULY 25–26, 2022")

dhamni = df[
    (df["Station"].str.strip().str.lower() == "dhamni") &
    (df[timestamp] >= "2022-07-25") &
    (df[timestamp] < "2022-07-27")
].sort_values(timestamp)

print(dhamni[
    ["Station", timestamp, rainfall]
].to_string(index=False))

# 3. Inspect other extreme stations
print("\nEXTREME READINGS BY STATION")

extreme = df[df[rainfall] > 50]

print(
    extreme.groupby("Station")[rainfall]
    .agg(["count", "mean", "max"])
    .sort_values("max", ascending=False)
    .head(15)
)

# 4. Save duplicate groups for review
duplicates.to_csv(
    DATA / "hourly_duplicate_groups_review.csv",
    index=False
)

print("\nSaved hourly_duplicate_groups_review.csv")