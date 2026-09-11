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

        rain_1h = latest_weather.rainfall_1h_mm if latest_weather else 0.0
        rain_3h = latest_weather.rainfall_3h_mm if latest_weather else 0.0
        rain_24h = latest_weather.rainfall_24h_mm if latest_weather else 0.0
        wind_speed = latest_weather.wind_speed_kmh if latest_weather else 15.0
        humidity = latest_weather.humidity_pct if latest_weather else 75.0
        tide_height = latest_weather.tide_height_m if (latest_weather and latest_weather.tide_height_m is not None) else 2.2

        # 2. Redis cached forecast check if available
        forecast_6h = 0.0
        forecast_12h = 0.0
        if r is not None:
            try:
                import json
                cached = await r.get(f"fip:weather:latest:{ward.ward_id}")
                if cached:
                    c_data = json.loads(cached)
                    forecast_6h = float(c_data.get("forecast_rain_6h_mm", 0.0))
                    forecast_12h = float(c_data.get("forecast_rain_12h_mm", 0.0))
            except Exception:
                pass

        # 3. Tide trend calculation (rising = +1, falling = -1)
        # Semi-diurnal cycle derivative
        hour_frac = (now.hour * 3600 + now.minute * 60) / 3600.0
        tide_trend = 1.0 if math.cos((hour_frac % 12.42) / 12.42 * 2 * math.pi) >= 0 else -1.0

        # 4. Crowdsourced reports within last 30 minutes
        citizen_count = 0
        citizen_avg_depth = 0.0
        citizen_confidence = 0.0
        if r is not None:
            try:
                cc = await r.get(f"fip:reports:count:{ward.ward_id}")
                cd = await r.get(f"fip:reports:avg_depth:{ward.ward_id}")
                cf = await r.get(f"fip:reports:conf:{ward.ward_id}")
                if cc:
                    citizen_count = int(cc)
                if cd:
                    citizen_avg_depth = float(cd)
                if cf:
                    citizen_confidence = float(cf)
            except Exception:
                pass

        # 5. Social NLP signals in last 30 minutes
        social_count = 0
        social_urgency = 0.0
        if r is not None:
            try:
                sc = await r.get(f"fip:social:count:{ward.ward_id}")
                su = await r.get(f"fip:social:urgency:{ward.ward_id}")
                if sc:
                    social_count = int(sc)
                if su:
                    social_urgency = float(su)
            except Exception:
                pass

        # 6. Static Topography & Drainage
        elevation_m = ward.avg_elevation_m if ward.avg_elevation_m is not None else 8.0
        elevation_std = 2.5  # standard terrain deviation across Mumbai coastal plains
        drainage_idx = ward.drainage_index if ward.drainage_index is not None else 0.5
        is_coastal_int = 1 if ward.is_coastal else 0
        area_sqkm = ward.area_sqkm if ward.area_sqkm is not None else 12.0

        # 7. Temporal Encodings
        temporal = self.compute_temporal_features(now)

        return {
            "ward_id": ward.ward_id,
            "rainfall_1h_mm": float(rain_1h),
            "rainfall_3h_mm": float(rain_3h),
            "rainfall_24h_mm": float(rain_24h),
            "wind_speed_kmh": float(wind_speed),
            "humidity_pct": float(humidity),
            "forecast_rain_6h_mm": float(forecast_6h),
            "forecast_rain_12h_mm": float(forecast_12h),
            "tide_height_m": float(tide_height) if ward.is_coastal else 0.0,
            "tide_trend": float(tide_trend) if ward.is_coastal else 0.0,
            "citizen_report_count": int(citizen_count),
            "citizen_avg_depth": float(citizen_avg_depth),
            "citizen_confidence": float(citizen_confidence),
            "social_signal_count": int(social_count),
            "social_urgency_score": float(social_urgency),
            "elevation_m": float(elevation_m),
            "elevation_std": float(elevation_std),
            "drainage_index": float(drainage_idx),
            "is_coastal": int(is_coastal_int),
            "area_sqkm": float(area_sqkm),
            "hour_sin": temporal["hour_sin"],
            "hour_cos": temporal["hour_cos"],
            "month_sin": temporal["month_sin"],
            "month_cos": temporal["month_cos"],
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
