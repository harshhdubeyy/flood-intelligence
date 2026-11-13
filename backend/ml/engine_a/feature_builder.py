"""
Feature vector builder for ML Engine A (XGBoost Inundation Classifier).
Constructs multi-modal feature matrices per ward combining weather,
hydrology, tidal levels, crowdsourced reports, social signals, and terrain indices.
"""
from __future__ import annotations

import math
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

import redis.asyncio as aioredis
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.ward import Ward
from backend.models.weather import WeatherSnapshot
from backend.models.report import CitizenReport
settings = get_settings()


class FeatureMatrixBuilder:
    """
    Builds the 18-dimension feature vector for each Mumbai ward conforming
    strictly to TRD Section 7.1.
    """

    def __init__(self):
        self.settings = settings
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> Any:
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(
                    self.settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                await self._redis.ping()
            except Exception:
                self._redis = None
        return self._redis

    def compute_temporal_features(self, dt: datetime) -> Dict[str, float]:
        """
        Compute continuous cyclical trigonometric encodings for hour-of-day and month-of-year.
        """
        hour = dt.hour + dt.minute / 60.0
        month = dt.month + (dt.day - 1) / 31.0

        hour_rad = 2 * math.pi * (hour / 24.0)
        month_rad = 2 * math.pi * (month / 12.0)

        return {
            "hour_sin": round(math.sin(hour_rad), 4),
            "hour_cos": round(math.cos(hour_rad), 4),
            "month_sin": round(math.sin(month_rad), 4),
            "month_cos": round(math.cos(month_rad), 4),
        }

    async def build_ward_features(
        self,
        session: AsyncSession,
        ward: Ward,
        now_dt: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Build individual feature dictionary for a single ward conforming to TRD 7.1.
        """
        now = now_dt or datetime.now(timezone.utc)
        r = await self._get_redis()

        # 1. Fetch latest weather snapshot for this ward
        snap_stmt = (
            select(WeatherSnapshot)
            .where(WeatherSnapshot.ward_id == ward.ward_id)
            .order_by(desc(WeatherSnapshot.fetched_at))
            .limit(1)
        )
        snap_res = await session.execute(snap_stmt)
        latest_weather = snap_res.scalar_one_or_none()

        weather_fresh = False
        weather_age_seconds: Optional[float] = None
        weather_fetched_at: Optional[str] = None
        weather_source: Optional[str] = None
        if latest_weather and latest_weather.fetched_at:
            w_fetched = latest_weather.fetched_at
            if w_fetched.tzinfo is None:
                w_fetched = w_fetched.replace(tzinfo=timezone.utc)
            weather_age_seconds = (now - w_fetched).total_seconds()
            weather_fresh = (-300 <= weather_age_seconds <= 7200)  # up to 2 hours
            weather_fetched_at = w_fetched.isoformat()
            weather_source = latest_weather.source or "Open-Meteo"

        # Missing values remain None (never zero-filled or fabricated)
        rain_1h = float(latest_weather.rainfall_1h_mm) if (latest_weather and latest_weather.rainfall_1h_mm is not None) else None
        rain_3h = float(latest_weather.rainfall_3h_mm) if (latest_weather and latest_weather.rainfall_3h_mm is not None) else None
        rain_24h = float(latest_weather.rainfall_24h_mm) if (latest_weather and latest_weather.rainfall_24h_mm is not None) else None
        wind_speed = float(latest_weather.wind_speed_kmh) if (latest_weather and latest_weather.wind_speed_kmh is not None) else None
        humidity = float(latest_weather.humidity_pct) if (latest_weather and latest_weather.humidity_pct is not None) else None
        tide_height = (float(latest_weather.tide_height_m) if (latest_weather and latest_weather.tide_height_m is not None and ward.is_coastal) else None)

        # 2. Redis cached forecast check (fresh if within 15 minutes TTL)
        forecast_6h: Optional[float] = None
        forecast_12h: Optional[float] = None
        forecast_fresh = False
        forecast_fetched_at: Optional[str] = None
        if r is not None:
            try:
                cached = await r.get(f"fip:weather:latest:{ward.ward_id}")
                if cached:
                    c_data = json.loads(cached)
                    ts = c_data.get("forecast_fetched_at_6h") or c_data.get("fetched_at")
                    if ts:
                        fetched_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if fetched_ts.tzinfo is None:
                            fetched_ts = fetched_ts.replace(tzinfo=timezone.utc)
                        f_age = (now - fetched_ts).total_seconds()
                        if -300 <= f_age <= 900:  # 15 minutes
                            forecast_fresh = True
                            forecast_fetched_at = ts
                            if c_data.get("forecast_rain_6h_mm") is not None:
                                forecast_6h = float(c_data["forecast_rain_6h_mm"])
                            if c_data.get("forecast_rain_12h_mm") is not None:
                                forecast_12h = float(c_data["forecast_rain_12h_mm"])
            except Exception:
                pass

        # 3. Tide trend calculation (rising = +1, falling = -1)
        hour_frac = (now.hour * 3600 + now.minute * 60) / 3600.0
        tide_trend = 1.0 if math.cos((hour_frac % 12.42) / 12.42 * 2 * math.pi) >= 0 else -1.0

        # 4. Crowdsourced reports within last 30 minutes from database
        thirty_min_ago = now - timedelta(minutes=30)
        from sqlalchemy import case
        rep_stmt = select(
            func.count(CitizenReport.id),
            func.avg(
                case(
                    (CitizenReport.water_depth == "ankle", 0.15),
                    (CitizenReport.water_depth == "knee", 0.50),
                    (CitizenReport.water_depth == "waist", 1.00),
                    (CitizenReport.water_depth == "submerged", 1.80),
                    else_=0.30,
                )
            ),
            func.avg(CitizenReport.cv_confidence),
        ).where(
            CitizenReport.ward_id == ward.ward_id,
            CitizenReport.is_duplicate.is_(False),
            CitizenReport.submitted_at >= thirty_min_ago,
        )
        rep_res = await session.execute(rep_stmt)
        rep_row = rep_res.first()
        citizen_count = int(rep_row[0] or 0) if rep_row else 0
        citizen_avg_depth = float(rep_row[1] or 0.0) if rep_row else 0.0
        citizen_confidence = float(rep_row[2] or 0.0) if rep_row else 0.0

        # 5. Social NLP signals in last 30 minutes (collection disabled)
        social_count = 0
        social_urgency = 0.0

        # 6. Static Topography & Drainage
        elevation_m = float(ward.avg_elevation_m) if ward.avg_elevation_m is not None else None
        elevation_std = 2.5  # standard terrain deviation across Mumbai coastal plains
        drainage_idx = float(ward.drainage_index) if ward.drainage_index is not None else None
        is_coastal_int = 1 if ward.is_coastal else 0
        area_sqkm = float(ward.area_sqkm) if ward.area_sqkm is not None else None

        # 7. Temporal Encodings
        temporal = self.compute_temporal_features(now)

        # 8. Provenance & Staleness Assessment
        is_stale = not weather_fresh
        stale_reasons: List[str] = []
        if latest_weather is None:
            stale_reasons.append("No weather snapshot available for this ward.")
        elif not weather_fresh:
            age_min = round(weather_age_seconds / 60.0, 1) if weather_age_seconds is not None else "unknown"
            stale_reasons.append(f"Weather snapshot is stale ({age_min}m old, threshold is 120m).")
        if not forecast_fresh:
            stale_reasons.append("Live per-ward forecast cache is expired or unavailable (15m TTL).")

        data_status = "fresh" if (weather_fresh and forecast_fresh) else ("stale" if latest_weather else "unavailable")

        provenance = {
            "weather": {
                "source": weather_source,
                "fetched_at": weather_fetched_at,
                "fresh": weather_fresh,
                "age_minutes": round(weather_age_seconds / 60.0, 1) if weather_age_seconds is not None else None,
            },
            "forecast": {
                "source": "Open-Meteo hourly cache" if forecast_fresh else None,
                "fetched_at": forecast_fetched_at,
                "fresh": forecast_fresh,
            },
            "citizen_reports": {
                "window": "last_30_minutes",
                "count": citizen_count,
            },
            "terrain": {
                "elevation_source": "ward_avg_elevation_m",
                "drainage_source": "ward_drainage_index",
            },
            "data_status": data_status,
            "is_stale": is_stale,
            "stale_reasons": stale_reasons,
        }

        return {
            "ward_id": ward.ward_id,
            "rainfall_1h_mm": rain_1h,
            "rainfall_3h_mm": rain_3h,
            "rainfall_24h_mm": rain_24h,
            "wind_speed_kmh": wind_speed,
            "humidity_pct": humidity,
            "forecast_rain_6h_mm": forecast_6h,
            "forecast_rain_12h_mm": forecast_12h,
            "tide_height_m": tide_height,
            "tide_trend": float(tide_trend) if ward.is_coastal else None,
            "citizen_report_count": citizen_count,
            "citizen_avg_depth": citizen_avg_depth,
            "citizen_confidence": citizen_confidence,
            "social_signal_count": social_count,
            "social_urgency_score": social_urgency,
            "elevation_m": elevation_m,
            "elevation_std": elevation_std,
            "drainage_index": drainage_idx,
            "is_coastal": is_coastal_int,
            "area_sqkm": area_sqkm,
            "hour_sin": temporal["hour_sin"],
            "hour_cos": temporal["hour_cos"],
            "month_sin": temporal["month_sin"],
            "month_cos": temporal["month_cos"],
            "is_stale": is_stale,
            "data_status": data_status,
            "stale_reasons": stale_reasons,
            "provenance": provenance,
        }

    async def build_citywide_matrix(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """
        Build feature vectors for all registered wards in Mumbai.
        """
        stmt = select(Ward).order_by(Ward.ward_id.asc())
        res = await session.execute(stmt)
        wards = res.scalars().all()

        features_list = []
        now = datetime.now(timezone.utc)
        for ward in wards:
            feat = await self.build_ward_features(session, ward, now)
            features_list.append(feat)

        return features_list


feature_builder = FeatureMatrixBuilder()
FeatureBuilder = FeatureMatrixBuilder
