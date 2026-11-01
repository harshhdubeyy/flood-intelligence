
import pandas as pd
from pathlib import Path

FILE = Path("backend/data/processed/rainfall_unified_mumbai_region.csv")

df = pd.read_csv(FILE)

df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

print("\n========== UNIFIED DATA VALIDATION ==========")

print("\n1. Record count:", len(df))

# Duplicate check
duplicate_count = df.duplicated(
    subset=["station", "timestamp", "temporal_resolution"]
).sum()

print("\n2. Duplicate records:", duplicate_count)

# Invalid values
print("\n3. Invalid timestamps:", df["timestamp"].isna().sum())
print("Missing station names:", df["station"].isna().sum())
print("Missing rainfall:", df["rainfall_mm"].isna().sum())

# Coordinates
print(
    "Invalid latitude:",
    ((df["latitude"] < -90) | (df["latitude"] > 90)).sum()
)

print(
    "Invalid longitude:",
    ((df["longitude"] < -180) | (df["longitude"] > 180)).sum()
)

# Negative rainfall
print(
    "Negative rainfall:",
    (df["rainfall_mm"] < 0).sum()
)

# Resolution-wise statistics
print("\n4. Resolution summary:")

print(
    df.groupby("temporal_resolution")
    .agg(
        records=("station", "size"),
        stations=("station", "nunique"),
        first_observation=("timestamp", "min"),
        last_observation=("timestamp", "max"),
        mean_rainfall=("rainfall_mm", "mean"),
        max_rainfall=("rainfall_mm", "max")
    ).to_string()
)

# Quality flags
print("\n5. Quality flags:")
print(df["quality_flag"].value_counts().to_string())

# Station-level coverage
print("\n6. Station counts by resolution:")
print(
    df.groupby("temporal_resolution")["station"]
    .nunique()
    .to_string()
)

print("\n========== VALIDATION COMPLETE ==========")
