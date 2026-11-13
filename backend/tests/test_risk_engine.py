"""
Automated unit and integration tests for Engine A Hydrological Risk Classifier
and Ward Risk Persistence.
"""

import math
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import select, func

from backend.ml.engine_a.xgboost_risk import (
    XGBoostRiskClassifier,
    risk_classifier,
    compute_ward_flood_risks,
)
from backend.models.database import async_session_factory
from backend.models.risk import WardRiskScore
from backend.models.ward import Ward


def test_evaluate_risk_honest_labelling_and_structure():
    classifier = XGBoostRiskClassifier()
    assert classifier.MODEL_VERSION == "heuristic-hydro-v1"
    assert len(classifier.MODEL_VERSION) <= 20

    features = {
        "ward_id": "BMC-A",
        "rainfall_1h_mm": 10.0,
        "rainfall_3h_mm": 20.0,
        "rainfall_24h_mm": 40.0,
        "forecast_rain_6h_mm": 15.0,
        "elevation_m": 8.0,
        "drainage_index": 0.5,
        "is_coastal": 1,
        "tide_height_m": 2.5,
        "tide_trend": -1.0,
        "citizen_report_count": 0,
        "citizen_avg_depth": 0.0,
        "is_stale": False,
        "data_status": "fresh",
    }

    score, r_class = classifier.evaluate_risk(features)
    assert 0.0 <= score <= 1.0
    assert r_class in ("low", "medium", "high", "critical")

    score2, r_class2, details = classifier.evaluate_risk(features, return_details=True)
    assert score == score2
    assert r_class == r_class2
    assert details["model_version"] == "heuristic-hydro-v1"
    assert details["method"] == "calibrated_hydrological_heuristic"
    assert "not a trained ML probability" in details["disclaimer"]
    assert details["status"] == "fresh"
    assert not details["is_stale"]


def test_evaluate_risk_missing_values_remain_missing():
    classifier = XGBoostRiskClassifier()

    # Features where 3h, 24h rain, forecast, and elevation are missing (None)
    features_with_missing = {
        "ward_id": "BMC-T",
        "rainfall_1h_mm": 5.0,
        "rainfall_3h_mm": None,
        "rainfall_24h_mm": None,
        "forecast_rain_6h_mm": None,
        "elevation_m": None,
        "drainage_index": 0.4,
        "is_coastal": 0,
        "tide_height_m": None,
        "tide_trend": None,
        "citizen_report_count": 0,
        "citizen_avg_depth": 0.0,
        "is_stale": False,
        "data_status": "fresh",
    }

    score, r_class, details = classifier.evaluate_risk(features_with_missing, return_details=True)
    assert 0.0 <= score <= 1.0
    assert r_class in ("low", "medium", "high", "critical")
    # Factors for missing domains should be None
    assert details["factors"]["topo_factor"] is None
    assert details["factors"]["tidal_factor"] is None
    # Rain factor was calculated solely from available 1h rainfall
    assert details["factors"]["rain_factor"] is not None
    assert details["factors"]["drainage_factor"] is not None


def test_evaluate_risk_stale_inputs_marked_explicitly():
    classifier = XGBoostRiskClassifier()

    stale_features = {
        "ward_id": "BMC-GN",
        "rainfall_1h_mm": 0.0,
        "rainfall_3h_mm": None,
        "rainfall_24h_mm": None,
        "forecast_rain_6h_mm": None,
        "elevation_m": 4.0,
        "drainage_index": 0.3,
        "is_coastal": 1,
        "tide_height_m": None,
        "is_stale": True,
        "data_status": "stale",
        "stale_reasons": ["Weather snapshot is stale (150m old)"],
    }

    score, r_class, details = classifier.evaluate_risk(stale_features, return_details=True)
    assert details["is_stale"] is True
    assert details["status"] == "stale"
    assert "Weather snapshot is stale" in details["stale_reasons"][0]


def test_evaluate_risk_high_severity_compound_synergy():
    classifier = XGBoostRiskClassifier()

    extreme_coastal = {
        "ward_id": "BMC-A",
        "rainfall_1h_mm": 55.0,  # Extreme rainfall (>45mm)
        "rainfall_3h_mm": 110.0,
        "rainfall_24h_mm": 200.0,
        "forecast_rain_6h_mm": 45.0,
        "elevation_m": 3.0,      # Low elevation
        "drainage_index": 0.2,   # Poor drainage
        "is_coastal": 1,
        "tide_height_m": 4.4,    # Critical tide surge
        "tide_trend": 1.0,       # Rising tide
        "citizen_report_count": 5,
        "citizen_avg_depth": 1.0,
        "is_stale": False,
        "data_status": "fresh",
    }

    score, r_class, details = classifier.evaluate_risk(extreme_coastal, return_details=True)
    assert score >= 0.75
    assert r_class == "critical"
    assert details["factors"]["tidal_factor"] > 0.5


@pytest.mark.asyncio
async def test_compute_and_persist_all_wards_live_execution():
    from backend.models.database import engine
    await engine.dispose()
    async with async_session_factory() as session:
        # Check ward count
        ward_count = await session.scalar(select(func.count(Ward.id)))
        assert ward_count == 24

        # Count risk scores before
        count_before = await session.scalar(select(func.count(WardRiskScore.id)))

        # Execute risk computation and persistence
        result = await compute_ward_flood_risks(session=session)
        assert result["status"] == "success"
        assert result["model_version"] == "heuristic-hydro-v1"
        assert result["wards_evaluated"] == 24
        assert "distribution" in result

        # Count risk scores after (should have incremented by 24)
        count_after = await session.scalar(select(func.count(WardRiskScore.id)))
        assert count_after == count_before + 24

        # Verify most recent persisted records
        recent_scores = (
            await session.execute(
                select(WardRiskScore)
                .order_by(WardRiskScore.computed_at.desc(), WardRiskScore.id.desc())
                .limit(24)
            )
        ).scalars().all()
        assert len(recent_scores) == 24

        ward_ids = {r.ward_id for r in recent_scores}
        assert len(ward_ids) == 24  # All 24 wards covered

        for r in recent_scores:
            assert 0.0 <= r.risk_score <= 1.0
            assert r.risk_class in ("low", "medium", "high", "critical")
            assert r.model_version == "heuristic-hydro-v1"
            assert isinstance(r.inputs_json, dict)
            assert r.inputs_json["method"] == "calibrated_hydrological_heuristic"
            assert "provenance" in r.inputs_json
            assert r.valid_until is not None
