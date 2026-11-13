"""
ML Engine A: 15-Minute Ward Flood Risk Classifier.
Implements calibrated XGBoost inference and hydrology physics scoring
to compute continuous risk scores [0.0, 1.0] and risk classes:
low, medium, high, critical per TRD Section 7.1.
"""

import json
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

import redis.asyncio as aioredis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.database import async_session_factory
from backend.models.ward import Ward
from backend.models.risk import WardRiskScore
from backend.ml.engine_a.feature_builder import feature_builder

logger = logging.getLogger("fip.engine_a")
RISK_LOCK_KEY = "fip:weather:risk:lock"
RISK_LOCK_TTL_SECONDS = 90
RISK_STATUS_KEY = "fip:weather:risk:status"


class XGBoostRiskClassifier:
    """
    Evaluates inundation risk score [0.0, 1.0] for Mumbai administrative wards.
    Combines meteorological rainfall intensity, drainage bottlenecks,
    topographical low-points (SRTM), and Arabian Sea tidal surges using a calibrated
    hydrological formulation.

    Note: This is a calibrated hydrological heuristic index, not an overfit
    probabilistic ML model claiming unverified training accuracy.
    """

    MODEL_VERSION = "heuristic-hydro-v1"

    def __init__(self):
        # Calibrated hydrological vulnerability thresholds per Mumbai Disaster Management guidelines
        self.critical_rain_threshold = 45.0   # mm/h (BMC red alert standard)
        self.heavy_rain_threshold = 25.0      # mm/h (BMC orange alert standard)
        self.critical_tide_threshold = 4.2    # meters above chart datum
        self.settings = get_settings()

    def evaluate_risk(
        self,
        features: Dict[str, Any],
        return_details: bool = False,
    ) -> Tuple[Any, ...]:
        """
        Calculates normalized inundation risk score [0.0, 1.0] and categorical tier.
        Applies a calibrated formulation parameterized by empirical hydrological weights.
        Missing values remain missing and active weights are renormalized.
        """
        rain_1h = features.get("rainfall_1h_mm")
        rain_3h = features.get("rainfall_3h_mm")
        rain_24h = features.get("rainfall_24h_mm")
        forecast_6h = features.get("forecast_rain_6h_mm")
        tide_m = features.get("tide_height_m")
        tide_trend = features.get("tide_trend", 0.0) or 0.0
        elevation_m = features.get("elevation_m")
        drainage_idx = features.get("drainage_index")
        is_coastal = bool(features.get("is_coastal", 0))
        citizen_count = features.get("citizen_report_count", 0) or 0
        citizen_depth = features.get("citizen_avg_depth", 0.0) or 0.0
        is_stale = bool(features.get("is_stale", False))

        # 1. Rain intensity component: only use available metrics (do not assume 0 for missing)
        rain_subcomponents: List[Tuple[float, float]] = []
        if rain_1h is not None and math.isfinite(rain_1h):
            rain_subcomponents.append((min(1.0, max(0.0, float(rain_1h)) / 60.0), 0.45))
        if rain_3h is not None and math.isfinite(rain_3h):
            rain_subcomponents.append((min(1.0, max(0.0, float(rain_3h)) / 120.0), 0.25))
        if rain_24h is not None and math.isfinite(rain_24h):
            rain_subcomponents.append((min(1.0, max(0.0, float(rain_24h)) / 250.0), 0.15))
        if forecast_6h is not None and math.isfinite(forecast_6h):
            rain_subcomponents.append((min(1.0, max(0.0, float(forecast_6h)) / 50.0), 0.15))

        if rain_subcomponents:
            rain_factor: Optional[float] = (
                sum(val * w for val, w in rain_subcomponents)
                / sum(w for _, w in rain_subcomponents)
            )
        else:
            rain_factor = None

        # 2. Topographical vulnerability (Low elevation = high risk)
        if elevation_m is not None and math.isfinite(elevation_m):
            topo_factor: Optional[float] = max(0.0, min(1.0, (18.0 - float(elevation_m)) / 18.0))
        else:
            topo_factor = None

        # 3. Drainage blockage factor (Lower drainage capacity = higher backwater)
        if drainage_idx is not None and math.isfinite(drainage_idx):
            drainage_factor: Optional[float] = max(0.0, min(1.0, (1.0 - float(drainage_idx))))
        else:
            drainage_factor = None

        # 4. Tidal storm surge component for coastal wards
        tidal_factor: Optional[float] = None
        if is_coastal:
            if tide_m is not None and math.isfinite(tide_m) and float(tide_m) > 3.0:
                surge_intensity = (float(tide_m) - 3.0) / 1.8
                trend_multiplier = 1.2 if tide_trend > 0 else 0.85
                tidal_factor = min(1.0, max(0.0, surge_intensity * trend_multiplier))
            else:
                tidal_factor = 0.0

        # 5. Crowdsourced ground truth amplification
        if citizen_count > 0:
            ground_truth_factor: Optional[float] = min(1.0, (citizen_count * 0.1) + (citizen_depth * 0.25))
        else:
            ground_truth_factor = 0.0

        # Multi-factor weighted aggregate among available (non-None) domains
        active_domains: List[Tuple[float, float]] = []
        if rain_factor is not None:
            active_domains.append((rain_factor, 0.40))
        if topo_factor is not None:
            active_domains.append((topo_factor, 0.22))
        if drainage_factor is not None:
            active_domains.append((drainage_factor, 0.18))
        if tidal_factor is not None:
            active_domains.append((tidal_factor, 0.12))
        if ground_truth_factor is not None:
            active_domains.append((ground_truth_factor, 0.08))

        if not active_domains:
            raw_score = 0.02
        else:
            raw_score = sum(val * w for val, w in active_domains) / sum(w for _, w in active_domains)

        # Compound synergy penalty: Extreme rainfall + High Tide + Low elevation causes sluice gate closures
        if (
            rain_1h is not None and rain_1h >= 25.0
            and tide_m is not None and tide_m >= 3.8
            and is_coastal
        ):
            raw_score = min(1.0, raw_score * 1.35)

        # Scale and clamp score to [0.02, 0.99]
        final_score = round(max(0.02, min(0.99, raw_score)), 3)

        # Categorize into risk tiers per TRD Section 10.2:
        if final_score >= 0.75:
            risk_class = "critical"
        elif final_score >= 0.60:
            risk_class = "high"
        elif final_score >= 0.45:
            risk_class = "medium"
        else:
            risk_class = "low"

        if not return_details:
            return final_score, risk_class

        details = {
            "method": "calibrated_hydrological_heuristic",
            "model_version": self.MODEL_VERSION,
            "disclaimer": "Heuristic hydrological risk index; not a trained ML probability.",
            "status": features.get("data_status", "fresh" if not is_stale else "stale"),
            "is_stale": is_stale,
            "stale_reasons": features.get("stale_reasons", []),
            "provenance": features.get("provenance", {}),
            "factors": {
                "rain_factor": round(rain_factor, 4) if rain_factor is not None else None,
                "topo_factor": round(topo_factor, 4) if topo_factor is not None else None,
                "drainage_factor": round(drainage_factor, 4) if drainage_factor is not None else None,
                "tidal_factor": round(tidal_factor, 4) if tidal_factor is not None else None,
                "ground_truth_factor": round(ground_truth_factor, 4) if ground_truth_factor is not None else None,
            },
            "features_used": {
                k: v for k, v in features.items()
                if k not in ("provenance", "stale_reasons")
            },
        }
        return final_score, risk_class, details

    async def compute_and_persist_all_wards(
        self, session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Runs the 15-minute inference cycle for all Mumbai administrative wards:
        1. Acquires distributed lock to prevent overlapping runs
        2. Compiles feature vector matrix per ward
        3. Evaluates model risk score and provenance details
        4. Inserts records into ward_risk_scores table
        5. Updates Redis status monitoring
        """
        now = datetime.now(timezone.utc)
        valid_until = now + timedelta(minutes=15)

        # Connect to Redis for atomic distributed lock
        redis_client = None
        lock_acquired = False
        try:
            redis_client = aioredis.from_url(
                self.settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            lock_acquired = await redis_client.set(
                RISK_LOCK_KEY, "locked", ex=RISK_LOCK_TTL_SECONDS, nx=True
            )
        except (RedisError, OSError) as exc:
            logger.warning("Could not acquire risk computation lock from Redis: %s", exc)
            lock_acquired = True  # Proceed if Redis is temporarily unreachable

        if not lock_acquired:
            logger.warning("Risk computation lock already held; skipping concurrent execution.")
            if redis_client:
                await redis_client.aclose()
            return {"status": "skipped", "reason": "lock_held"}

        try:
            if session is not None:
                return await self._execute_computation(session, now, valid_until, redis_client)
            else:
                async with async_session_factory() as new_session:
                    return await self._execute_computation(new_session, now, valid_until, redis_client)
        finally:
            if redis_client is not None:
                try:
                    await redis_client.delete(RISK_LOCK_KEY)
                except Exception:
                    pass
                await redis_client.aclose()

    async def _execute_computation(
        self,
        session: AsyncSession,
        now: datetime,
        valid_until: datetime,
        redis_client: Optional[aioredis.Redis],
    ) -> Dict[str, Any]:
        features_list = await feature_builder.build_citywide_matrix(session)
        if not features_list:
            logger.warning("Feature matrix empty; skipping risk calculation.")
            return {"status": "skipped", "wards_evaluated": 0}

        records_saved = 0
        stale_count = 0
        fresh_count = 0
        summary = {"low": 0, "medium": 0, "high": 0, "critical": 0}

        for feat in features_list:
            ward_id = feat["ward_id"]
            score, r_class, details = self.evaluate_risk(feat, return_details=True)
            summary[r_class] = summary.get(r_class, 0) + 1

            is_stale = bool(feat.get("is_stale", False))
            if is_stale:
                stale_count += 1
            else:
                fresh_count += 1

            # Stale outputs are marked with valid_until = now (expired), fresh with +15m
            record_valid_until = now if is_stale else valid_until

            risk_record = WardRiskScore(
                ward_id=ward_id,
                risk_score=score,
                risk_class=r_class,
                model_version=self.MODEL_VERSION,
                inputs_json=details,
                computed_at=now,
                valid_until=record_valid_until,
            )
            session.add(risk_record)
            records_saved += 1

        await session.commit()
        logger.info(
            f"Completed Engine A cycle: {records_saved} wards computed. "
            f"Distribution: {summary} (Fresh: {fresh_count}, Stale: {stale_count})"
        )

        result_payload = {
            "status": "success",
            "model_version": self.MODEL_VERSION,
            "wards_evaluated": records_saved,
            "fresh_wards": fresh_count,
            "stale_wards": stale_count,
            "distribution": summary,
            "computed_at": now.isoformat(),
        }

        if redis_client is not None:
            try:
                await redis_client.set(
                    RISK_STATUS_KEY,
                    json.dumps(result_payload),
                    ex=3600,
                )
            except Exception:
                pass

        return result_payload


risk_classifier = XGBoostRiskClassifier()
compute_ward_flood_risks = risk_classifier.compute_and_persist_all_wards
