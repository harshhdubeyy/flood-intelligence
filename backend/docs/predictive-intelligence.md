# Predictive flood intelligence

## What the outlook means

The service currently returns a **heuristic scenario index**, not a trained flood model and not a probability. No validated historical ward-level flood outcome labels or temporal model evaluation are available in the repository. Accordingly, `predicted_probability` is always `null`, no precision/recall/AUC/Brier score is claimed, and a ward receives no outlook score unless a fresh per-ward precipitation forecast exists for the selected horizon.

The existing Engine A score remains a separate current-risk-engine signal. It is included only when its saved score is no more than 30 minutes old. It is not treated as an observed flood measurement or as a validated probability.

## Inputs and provenance

- Open-Meteo forecast accumulations are read from the existing per-ward Redis cache. The ingestion pipeline now stores complete 1-, 3-, 6-, 12-, and 24-hour accumulations. A missing interval, incomplete horizon, stale cache entry, or unavailable Redis cache remains missing; it is never interpreted as zero rainfall. Forecast cache entries are considered fresh for 15 minutes.
- Weather snapshot rainfall, humidity, and wind values are used only when a snapshot is no more than two hours old. The database does not currently store observed 6- or 12-hour rain, forecast records, weather alerts, or measured tide forecasts; those features remain `null`.
- Elevation, drainage index, and coastal status are used only when present on the ward row. A missing ward row does not receive fabricated geography or a fabricated ward ID.
- Citizen evidence is aggregated from non-duplicate reports submitted in the previous 24 hours. Counts and CV-verified proportions are separated from the existing citizen-intelligence score and from current risk.
- `ward_rainfall_coverage.csv` contributes station provenance only. In this repository its nearest hourly stations are 13.86–48.58 km from wards and the reported records end in 2025; daily coverage ends earlier. These historical point records are not treated as current ward rainfall. Three- and seven-day rain accumulation, historical intensity/trend, and station-derived live rain therefore remain unavailable.
- All 24 ward codes in the existing rainfall coverage catalog are returned. A code without a matching database ward row has `ward_id: null`; because the live forecast cache is keyed from registered ward rows, these wards remain unavailable until ward records and forecasts are registered.

## Scenario-index formula

The index is intentionally transparent and not empirically fitted:

1. `rain_factor = clamp(forecast_mm / (25 * horizon_hours), 0, 1)`. The 25 mm/hour scale references the existing Engine A heavy-rain threshold; it is a scenario scale, not a validated flood threshold.
2. `vulnerability_factor` is the mean of the available geographic components: `clamp((18 - elevation_m) / 18, 0, 1)` and `clamp(1 - drainage_index, 0, 1)`. Missing components are omitted.
3. `citizen_factor = min(severe_non_duplicate_reports_24h / 3, 1) * (0.7 + 0.3 * cv_verified_proportion_24h)`.
4. The score is the weighted mean of available components using weights 0.70, 0.20, and 0.10 for rainfall, geography, and citizen evidence. Missing geography weights are omitted and remaining weights are renormalized. The report query is available even when it returns zero rows; zero reports mean no citizen evidence, not proof of no flooding.
5. Categories use index bands: low `<0.25`, moderate `0.25–<0.50`, high `0.50–<0.75`, and critical `>=0.75`.

`data_completeness` indicates whether the forecast, geography, and citizen-data domains were available. It is an availability indicator, not statistical confidence. Explanations are emitted only for factors present in the feature vector.

## API and evaluation limits

- `GET /v1/predictions/wards?horizon=6h`
- `GET /v1/predictions/wards/{ward_id}?horizon=6h`
- `GET /v1/predictions/summary?horizon=6h`

Only horizons with at least one fresh forecast are listed in `supported_horizons`; other wards remain explicitly unavailable. Prediction history is not persisted, so increasing-risk counts and historical model evaluation are unavailable. No prediction-history migration is required until reliable outcome labels and a validation/evaluation workflow exist.
