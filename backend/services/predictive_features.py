"""Build provenance-aware ward features and a non-probabilistic outlook index.

The outlook is deliberately not called a prediction probability: there are no
validated flood outcome labels in this repository. A score is emitted only
when a fresh weather forecast is available for that ward and horizon.
"""

import csv
import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional

import redis.asyncio as redis
from redis.exceptions import RedisError
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.report import CitizenReport
from backend.models.risk import WardRiskScore
from backend.models.ward import Ward
from backend.models.weather import WeatherSnapshot
from backend.services.report_intelligence import ReportIntelligenceEngine

logger = logging.getLogger("fip.services.predictive_features")

ForecastHorizon = Literal["1h", "3h", "6h", "12h", "24h"]
FORECAST_HORIZONS: tuple[ForecastHorizon, ...] = ("1h", "3h", "6h", "12h", "24h")
HORIZON_HOURS = {f"{hours}h": hours for hours in (1, 3, 6, 12, 24)}
FORECAST_CACHE_TTL = timedelta(minutes=15)
WEATHER_SNAPSHOT_MAX_AGE = timedelta(hours=2)
CURRENT_RISK_MAX_AGE = timedelta(minutes=30)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WARD_COVERAGE_PATH = PROJECT_ROOT / "backend/data/processed/ward_rainfall_coverage.csv"


def normalize_ward_code(value: Optional[str]) -> str:
    """Normalize ward codes for matching without inventing missing ward IDs."""
    normalized = re.sub(r"^(?:MH[-_]*)?BMC[-_]*", "", (value or "").strip().upper())
    return re.sub(r"[^A-Z0-9]", "", normalized)


@lru_cache(maxsize=1)
def load_rainfall_coverage() -> dict[str, dict[str, Any]]:
    """Read nearest-station metadata; station observations are not used as live rain."""
    coverage: dict[str, dict[str, Any]] = {}
    with WARD_COVERAGE_PATH.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            code = normalize_ward_code(row.get("ward_name"))
            dataset = row.get("dataset", "").strip().lower()
            if not code or dataset not in {"hourly", "daily"}:
                continue
            try:
                distance = float(row["distance_to_ward_km"])
            except (KeyError, TypeError, ValueError):
                logger.warning("Skipping rainfall coverage row with invalid distance: %s", row)
                continue

            dataset_key = f"nearest_{dataset}_station"
            previous = coverage.setdefault(code, {}).get(dataset_key)
            if previous is None or distance < previous["distance_km"]:
                coverage[code][dataset_key] = {
                    "station": row.get("station"),
                    "distance_km": distance,
                    "last_record": row.get("last_record"),
                }
    return coverage


@dataclass
class WardFeatureVector:
    ward_code: str
    ward_id: Optional[str]
    ward_name: str
    features: dict[str, Any]
    availability: dict[str, bool]
    provenance: dict[str, Any]
    current_risk_score: Optional[float]
    current_risk_category: Optional[str]
    current_risk_computed_at: Optional[datetime]
    current_risk_model_version: Optional[str]


def classify_outlook_score(score: float) -> str:
    """Qualitative bands for the heuristic index; these are not probabilities."""
    if score >= 0.75:
        return "critical"
    if score >= 0.50:
        return "high"
    if score >= 0.25:
        return "moderate"
    return "low"


def _fresh_timestamp(value: Any, now: datetime, max_age: timedelta) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed > now + timedelta(minutes=5) or now - parsed > max_age:
        return None
    return parsed


def _utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalize(value: Optional[float], scale: float) -> Optional[float]:
    if value is None:
        return None
    return round(max(0.0, min(1.0, value / scale)), 4)


def build_outlook(vector: WardFeatureVector, horizon: ForecastHorizon, now: datetime) -> dict[str, Any]:
    """Return a heuristic rainfall outlook index, never a calibrated probability.

    The index combines forecast rainfall (70%), available geographic
    vulnerability (20%), and recent non-duplicate citizen evidence (10%).
    Missing geographic inputs are omitted and the remaining weights are
    renormalized. Forecast rainfall is normalized to 25 mm/hour, the existing
    Engine A heavy-rain reference threshold. These weights and bands are
    transparent operational assumptions, not empirically fitted parameters.
    """
    forecast_key = f"forecast_rainfall_{horizon}_mm"
    forecast_rain = vector.features.get(forecast_key)
    common = {
        "ward_id": vector.ward_id,
        "ward_code": vector.ward_code,
        "ward_name": vector.ward_name,
        "horizon": horizon,
        "prediction_timestamp": now,
        "model_version": "heuristic-outlook-v1",
        "current_risk_score": vector.current_risk_score,
        "current_risk_category": vector.current_risk_category,
        "current_risk_computed_at": vector.current_risk_computed_at,
        "current_risk_model_version": vector.current_risk_model_version,
        "predicted_probability": None,
    }

    if not isinstance(forecast_rain, (int, float)) or not math.isfinite(float(forecast_rain)):
        forecast_provenance = vector.provenance.get("forecast", {})
        unavailable_reason = (
            "The live forecast cache is unavailable."
            if forecast_provenance.get("cache_error")
            else "No fresh per-ward precipitation forecast is available for this horizon."
        )
        return {
            **common,
            "status": "unavailable",
            "predicted_risk_score": None,
            "risk_category": None,
            "data_completeness": 0.0,
            "contributing_factors": [],
            "unavailable_reason": unavailable_reason,
        }

    hours = HORIZON_HOURS[horizon]
    forecast_factor = min(1.0, max(0.0, float(forecast_rain)) / (25.0 * hours))
    elevation = vector.features.get("elevation_m")
    drainage = vector.features.get("drainage_index")
    geographic_components = []
    if isinstance(elevation, (int, float)):
        geographic_components.append(max(0.0, min(1.0, (18.0 - float(elevation)) / 18.0)))
    if isinstance(drainage, (int, float)):
        geographic_components.append(max(0.0, min(1.0, 1.0 - float(drainage))))
    vulnerability_factor = (
        sum(geographic_components) / len(geographic_components)
        if geographic_components else None
    )

    severe_reports = vector.features.get("severe_reports_24h")
    verified_ratio = vector.features.get("cv_verified_proportion_24h")
    citizen_factor = None
    if isinstance(severe_reports, int) and isinstance(verified_ratio, (int, float)):
        citizen_factor = min(1.0, severe_reports / 3.0) * (0.7 + 0.3 * float(verified_ratio))

    weighted_components = [(forecast_factor, 0.70)]
    if vulnerability_factor is not None:
        weighted_components.append((vulnerability_factor, 0.20))
    if citizen_factor is not None:
        weighted_components.append((citizen_factor, 0.10))
    weight_total = sum(weight for _, weight in weighted_components)
    score = sum(value * weight for value, weight in weighted_components) / weight_total
    score = round(max(0.0, min(1.0, score)), 3)

    available_domains = 1 + int(vulnerability_factor is not None) + int(citizen_factor is not None)
    completeness = round(available_domains / 3, 2)
    factors = [f"Forecast precipitation: {float(forecast_rain):.1f} mm over {hours} hours."]
    if vulnerability_factor is not None and vulnerability_factor >= 0.35:
        factors.append("Ward elevation or drainage characteristics increase geographic vulnerability.")
    if isinstance(severe_reports, int) and severe_reports > 0:
        factors.append(
            f"{severe_reports} non-duplicate severe citizen report(s) were submitted in the last 24 hours."
        )

    return {
        **common,
        "status": "available" if completeness == 1 else "low_confidence",
        "predicted_risk_score": score,
        "risk_category": classify_outlook_score(score),
        "data_completeness": completeness,
        "contributing_factors": factors,
        "unavailable_reason": None,
    }


class PredictiveFeatureService:
    """Assemble observed, forecast, geographic, and citizen features per ward."""

    def __init__(self, db: AsyncSession, redis_client: Any = None):
        self.db = db
        self.redis_client = redis_client

    async def _forecast_cache(self, ward_ids: list[str], now: datetime) -> tuple[dict[str, dict[str, Any]], Optional[str]]:
        client = self.redis_client
        owns_client = client is None
        if client is None:
            client = redis.from_url(
                get_settings().redis_url,
                encoding="utf-8",
                decode_responses=True,
            )

        forecasts: dict[str, dict[str, Any]] = {}
        try:
            await client.ping()
            for ward_id in ward_ids:
                raw = await client.get(f"fip:weather:latest:{ward_id}")
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Ignoring malformed forecast cache for ward %s.", ward_id)
                    continue
                forecast_values = {}
                horizon_timestamps = []
                has_horizon_timestamps = any(
                    payload.get(f"forecast_fetched_at_{horizon}")
                    for horizon in FORECAST_HORIZONS
                )
                for horizon in FORECAST_HORIZONS:
                    key = f"forecast_rain_{horizon}_mm"
                    value = _finite_number(payload.get(key))
                    fetched_at = _fresh_timestamp(
                        payload.get(f"forecast_fetched_at_{horizon}"),
                        now,
                        FORECAST_CACHE_TTL,
                    )
                    if not has_horizon_timestamps:
                        fetched_at = _fresh_timestamp(payload.get("fetched_at"), now, FORECAST_CACHE_TTL)
                    if value is not None and fetched_at is not None:
                        horizon_timestamps.append(fetched_at)
                    else:
                        value = None
                    forecast_values[f"forecast_rainfall_{horizon}_mm"] = (
                        max(0.0, value) if value is not None else None
                    )
                if not horizon_timestamps:
                    continue
                forecasts[ward_id] = {
                    **forecast_values,
                    "fetched_at": max(horizon_timestamps),
                    "source": "Open-Meteo hourly forecast cache",
                }
        except (RedisError, OSError) as exc:
            logger.warning("Predictive forecast cache is unavailable: %s", exc)
            return {}, "Fresh forecast cache is unavailable."
        finally:
            if owns_client:
                await client.aclose()
        return forecasts, None

    async def build_citywide_features(self, now: Optional[datetime] = None) -> list[WardFeatureVector]:
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        coverage = load_rainfall_coverage()
        ward_rows = (await self.db.execute(select(Ward).order_by(Ward.ward_id.asc()))).scalars().all()
        wards_by_code = {normalize_ward_code(ward.ward_id): ward for ward in ward_rows}
        ward_codes = set(coverage) | set(wards_by_code)

        weather_by_id: dict[str, WeatherSnapshot] = {}
        risk_by_id: dict[str, WardRiskScore] = {}
        ward_ids = [ward.ward_id for ward in ward_rows]
        if ward_ids:
            weather_rows = (
                await self.db.execute(
                    select(WeatherSnapshot)
                    .where(WeatherSnapshot.ward_id.in_(ward_ids))
                    .order_by(desc(WeatherSnapshot.fetched_at))
                )
            ).scalars().all()
            for snapshot in weather_rows:
                if snapshot.ward_id and snapshot.ward_id not in weather_by_id:
                    weather_by_id[snapshot.ward_id] = snapshot

            risk_rows = (
                await self.db.execute(
                    select(WardRiskScore)
                    .where(WardRiskScore.ward_id.in_(ward_ids))
                    .order_by(desc(WardRiskScore.computed_at))
                )
            ).scalars().all()
            for risk in risk_rows:
                if risk.ward_id and risk.ward_id not in risk_by_id:
                    risk_by_id[risk.ward_id] = risk

        forecast_by_id, forecast_error = await self._forecast_cache(ward_ids, current_time)

        report_since = current_time - timedelta(hours=24)
        report_rows = (
            await self.db.execute(
                select(
                    CitizenReport.ward_id,
                    CitizenReport.water_depth,
                    CitizenReport.cv_verified,
                    CitizenReport.submitted_at,
                ).where(
                    CitizenReport.is_duplicate.is_(False),
                    CitizenReport.submitted_at >= report_since,
                    CitizenReport.ward_id.is_not(None),
                )
            )
        ).all()
        reports_by_code: dict[str, list[Any]] = {}
        for row in report_rows:
            code = normalize_ward_code(row.ward_id)
            if code:
                reports_by_code.setdefault(code, []).append(row)

        intelligence_service = ReportIntelligenceEngine(self.db)
        hotspots = await intelligence_service.detect_hotspots()
        hotspot_counts: dict[str, int] = {}
        for hotspot in hotspots:
            for ward_id in hotspot.get("ward_ids", []):
                code = normalize_ward_code(ward_id)
                hotspot_counts[code] = hotspot_counts.get(code, 0) + 1

        intelligence_by_code: dict[str, Optional[dict[str, Any]]] = {}
        for ward in ward_rows:
            code = normalize_ward_code(ward.ward_id)
            if reports_by_code.get(code):
                intelligence_by_code[code] = await intelligence_service.calculate_ward_intelligence_score(
                    ward.ward_id,
                    hotspots=hotspots,
                )

        vectors = []
        for code in sorted(ward_codes):
            ward = wards_by_code.get(code)
            ward_id = ward.ward_id if ward else None
            snapshot = weather_by_id.get(ward_id) if ward_id else None
            snapshot_at = _utc_datetime(snapshot.fetched_at) if snapshot else None
            snapshot_age = current_time - snapshot_at if snapshot_at else None
            snapshot_fresh = bool(
                snapshot_age is not None
                and timedelta(minutes=-5) <= snapshot_age <= WEATHER_SNAPSHOT_MAX_AGE
            )

            forecast = forecast_by_id.get(ward_id, {}) if ward_id else {}
            report_list = reports_by_code.get(code, [])
            reports_1h = [
                row for row in report_list
                if row.submitted_at >= current_time - timedelta(hours=1)
            ]
            reports_3h = [
                row for row in report_list
                if row.submitted_at >= current_time - timedelta(hours=3)
            ]
            reports_previous_3h = [
                row for row in report_list
                if current_time - timedelta(hours=6) <= row.submitted_at < current_time - timedelta(hours=3)
            ]
            severe_reports = sum(
                row.water_depth in {"waist", "submerged"} for row in report_list
            )
            verified_count = sum(bool(row.cv_verified) for row in report_list)
            report_count = len(report_list)
            latest_risk = risk_by_id.get(ward_id) if ward_id else None
            risk_at = _utc_datetime(latest_risk.computed_at) if latest_risk else None
            risk_age = current_time - risk_at if risk_at else None
            risk_is_fresh = bool(
                risk_age is not None
                and timedelta(minutes=-5) <= risk_age <= CURRENT_RISK_MAX_AGE
            )

            features = {
                "rainfall_1h_mm": _finite_number(snapshot.rainfall_1h_mm) if snapshot_fresh else None,
                "rainfall_3h_mm": _finite_number(snapshot.rainfall_3h_mm) if snapshot_fresh else None,
                "rainfall_6h_mm": None,
                "rainfall_12h_mm": None,
                "rainfall_24h_mm": _finite_number(snapshot.rainfall_24h_mm) if snapshot_fresh else None,
                "rainfall_3d_mm": None,
                "rainfall_7d_mm": None,
                "rainfall_intensity_mmph": _finite_number(snapshot.rainfall_1h_mm) if snapshot_fresh else None,
                "rainfall_trend_mmph": None,
                "forecast_rainfall_1h_mm": forecast.get("forecast_rainfall_1h_mm"),
                "forecast_rainfall_3h_mm": forecast.get("forecast_rainfall_3h_mm"),
                "forecast_rainfall_6h_mm": forecast.get("forecast_rainfall_6h_mm"),
                "forecast_rainfall_12h_mm": forecast.get("forecast_rainfall_12h_mm"),
                "forecast_rainfall_24h_mm": forecast.get("forecast_rainfall_24h_mm"),
                "humidity_pct": _finite_number(snapshot.humidity_pct) if snapshot_fresh else None,
                "wind_speed_kmh": _finite_number(snapshot.wind_speed_kmh) if snapshot_fresh else None,
                "weather_alerts": None,
                "elevation_m": _finite_number(ward.avg_elevation_m) if ward else None,
                "drainage_index": _finite_number(ward.drainage_index) if ward else None,
                "is_coastal": bool(ward.is_coastal) if ward else None,
                "rainfall_station_coverage": coverage.get(code, {}),
                "recent_report_count_1h": len(reports_1h),
                "recent_report_count_3h": len(reports_3h),
                "recent_report_count_24h": report_count,
                "report_trend_3h": len(reports_3h) - len(reports_previous_3h),
                "severe_reports_24h": severe_reports,
                "cv_verified_proportion_24h": verified_count / report_count if report_count else 0.0,
                "hotspot_count_24h": hotspot_counts.get(code, 0),
                "citizen_intelligence_score": (
                    intelligence_by_code.get(code, {}).get("intelligence_score")
                    if intelligence_by_code.get(code) else None
                ),
            }
            for hours in (1, 3, 6, 12, 24, 72, 168):
                feature_key = f"rainfall_{hours if hours < 72 else hours // 24}h_mm"
                if hours == 72:
                    feature_key = "rainfall_3d_mm"
                elif hours == 168:
                    feature_key = "rainfall_7d_mm"
                features[f"{feature_key.removesuffix('_mm')}_normalized"] = _normalize(
                    features[feature_key],
                    25.0 * hours,
                )
                forecast_key = f"forecast_rainfall_{hours}h_mm"
                if forecast_key in features:
                    features[f"forecast_rainfall_{hours}h_normalized"] = _normalize(
                        features[forecast_key],
                        25.0 * hours,
                    )
            features["rainfall_intensity_normalized"] = _normalize(
                features["rainfall_intensity_mmph"],
                25.0,
            )
            features["elevation_vulnerability_normalized"] = (
                max(0.0, min(1.0, (18.0 - features["elevation_m"]) / 18.0))
                if features["elevation_m"] is not None else None
            )
            features["drainage_vulnerability_normalized"] = (
                max(0.0, min(1.0, 1.0 - features["drainage_index"]))
                if features["drainage_index"] is not None else None
            )
            features["severe_reports_24h_normalized"] = min(1.0, severe_reports / 3.0)
            features["hotspot_density_24h_normalized"] = min(1.0, hotspot_counts.get(code, 0) / 3.0)
            features["rainfall_trend_normalized"] = None
            forecast_values_available = any(
                features[f"forecast_rainfall_{horizon}_mm"] is not None
                for horizon in FORECAST_HORIZONS
            )
            hourly_coverage = features["rainfall_station_coverage"].get("nearest_hourly_station", {})
            daily_coverage = features["rainfall_station_coverage"].get("nearest_daily_station", {})
            provenance = {
                "weather_snapshot": {
                    "source": snapshot.source if snapshot and snapshot_fresh else None,
                    "fetched_at": snapshot_at if snapshot_fresh else None,
                    "fresh": snapshot_fresh,
                },
                "forecast": {
                    "source": forecast.get("source"),
                    "fetched_at": forecast.get("fetched_at"),
                    "fresh": bool(forecast),
                    "cache_error": forecast_error,
                },
                "historical_rainfall": {
                    "hourly_nearest_station": hourly_coverage,
                    "daily_nearest_station": daily_coverage,
                    "used_as_current_input": False,
                    "reason": "Station records are historical and spatially distant; no current accumulation is inferred.",
                },
                "citizen_reports": {
                    "source": "citizen_reports table; duplicates excluded; submitted within 24 hours",
                    "count": report_count,
                    "as_of": current_time,
                    "window_start": report_since,
                },
                "geospatial": "wards table" if ward else "No registered ward metadata in the database.",
            }
            availability = {
                "observed_rainfall": any(
                    features[key] is not None
                    for key in ("rainfall_1h_mm", "rainfall_3h_mm", "rainfall_24h_mm")
                ),
                "forecast": forecast_values_available,
                "geospatial": features["elevation_m"] is not None or features["drainage_index"] is not None,
                "citizen_reports": True,
                "citizen_hotspots": True,
                "historical_rainfall": False,
                "weather_alerts": False,
            }
            vectors.append(
                WardFeatureVector(
                    ward_code=code,
                    ward_id=ward_id,
                    ward_name=ward.ward_name if ward else code,
                    features=features,
                    availability=availability,
                    provenance=provenance,
                    current_risk_score=(
                        float(latest_risk.risk_score) if risk_is_fresh and latest_risk else None
                    ),
                    current_risk_category=(
                        str(latest_risk.risk_class) if risk_is_fresh and latest_risk else None
                    ),
                    current_risk_computed_at=(
                        risk_at if risk_is_fresh else None
                    ),
                    current_risk_model_version=(
                        latest_risk.model_version if risk_is_fresh and latest_risk else None
                    ),
                )
            )
        return vectors


def prediction_from_features(
    vector: WardFeatureVector,
    horizon: ForecastHorizon,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Combine the feature vector and explicit scenario assumptions."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    outlook = build_outlook(vector, horizon, current_time)
    return {
        **outlook,
        "feature_vector": vector.features,
        "data_availability": vector.availability,
        "feature_provenance": vector.provenance,
    }
