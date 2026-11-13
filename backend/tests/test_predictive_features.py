"""Tests for missing-data handling and the explicitly heuristic outlook."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx

from backend.pipeline.weather_ingest import WeatherIngestService, _forecast_accumulation
from backend.pipeline.weather_ingest import _has_fresh_cached_forecast, _merge_weather_cache
from backend.services.predictive_features import (
    PredictiveFeatureService,
    WardFeatureVector,
    build_outlook,
    classify_outlook_score,
    load_rainfall_coverage,
)


def _vector(features, provenance=None):
    return WardFeatureVector(
        ward_code="A",
        ward_id="BMC-A",
        ward_name="Colaba",
        features=features,
        availability={},
        provenance=provenance or {},
        current_risk_score=None,
        current_risk_category=None,
        current_risk_computed_at=None,
        current_risk_model_version=None,
    )


def test_missing_forecast_does_not_create_an_outlook_score():
    result = build_outlook(_vector({"forecast_rainfall_6h_mm": None}), "6h", datetime.now(timezone.utc))

    assert result["status"] == "unavailable"
    assert result["predicted_risk_score"] is None
    assert result["predicted_probability"] is None
    assert result["contributing_factors"] == []


def test_forecast_cache_failure_is_exposed_as_unavailable_reason():
    result = build_outlook(
        _vector(
            {"forecast_rainfall_6h_mm": None},
            {"forecast": {"cache_error": "Fresh forecast cache is unavailable."}},
        ),
        "6h",
        datetime.now(timezone.utc),
    )

    assert result["unavailable_reason"] == "The live forecast cache is unavailable."


def test_complete_feature_set_uses_documented_heuristic_formula():
    result = build_outlook(
        _vector({
            "forecast_rainfall_6h_mm": 75.0,
            "elevation_m": 9.0,
            "drainage_index": 0.2,
            "severe_reports_24h": 2,
            "cv_verified_proportion_24h": 0.5,
        }),
        "6h",
        datetime.now(timezone.utc),
    )

    assert result["predicted_risk_score"] == 0.537
    assert result["risk_category"] == "high"
    assert result["status"] == "available"
    assert result["data_completeness"] == 1.0
    assert result["predicted_probability"] is None
    assert len(result["contributing_factors"]) == 3


def test_missing_geography_is_omitted_and_weights_are_renormalized():
    result = build_outlook(
        _vector({"forecast_rainfall_3h_mm": 37.5}),
        "3h",
        datetime.now(timezone.utc),
    )

    assert result["predicted_risk_score"] == 0.5
    assert result["status"] == "low_confidence"
    assert result["data_completeness"] == 0.33


def test_forecast_sums_preserve_missing_intervals_but_accept_real_zeroes():
    assert _forecast_accumulation([1.0, None, 2.0], 3) is None
    assert _forecast_accumulation([1.0, 2.0], 3) is None
    assert _forecast_accumulation([0.0, 0.0, 0.0], 3) == 0.0


def test_forecast_accumulation_skips_elapsed_hours():
    result = _forecast_accumulation(
        [90.0, 1.0, 2.0, 3.0],
        3,
        ["2026-01-01T17:00", "2026-01-01T18:00", "2026-01-01T19:00", "2026-01-01T20:00"],
        datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc),
    )

    assert result == 6.0


def test_open_meteo_retries_transient_provider_errors(monkeypatch):
    async def run():
        requests = 0

        async def handler(request):
            nonlocal requests
            requests += 1
            if requests == 1:
                return httpx.Response(503, request=request)
            return httpx.Response(200, json={"hourly": {"time": []}}, request=request)

        monkeypatch.setattr("backend.pipeline.weather_ingest.asyncio.sleep", AsyncMock())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await WeatherIngestService().fetch_open_meteo_forecast(client, 19.0, 72.8)
        return requests, result

    requests, result = asyncio.run(run())

    assert requests == 2
    assert result == {"hourly": {"time": []}}


def test_open_meteo_reports_unavailable_after_bounded_retries(monkeypatch):
    async def run():
        requests = 0

        async def handler(request):
            nonlocal requests
            requests += 1
            return httpx.Response(503, request=request)

        monkeypatch.setattr("backend.pipeline.weather_ingest.asyncio.sleep", AsyncMock())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await WeatherIngestService().fetch_open_meteo_forecast(client, 19.0, 72.8)
        return requests, result

    requests, result = asyncio.run(run())

    assert requests == 3
    assert result == {}


def test_openweathermap_retries_transient_provider_errors(monkeypatch):
    async def run():
        requests = 0
        service = WeatherIngestService()
        service.settings.openweathermap_api_key = "test-key"

        async def handler(request):
            nonlocal requests
            requests += 1
            if requests == 1:
                return httpx.Response(503, request=request)
            return httpx.Response(200, json={"main": {"humidity": 60}}, request=request)

        monkeypatch.setattr("backend.pipeline.weather_ingest.asyncio.sleep", AsyncMock())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await service.fetch_openweathermap_current(client, 19.0, 72.8)
        return requests, result

    requests, result = asyncio.run(run())

    assert requests == 2
    assert result == {"main": {"humidity": 60}}


def test_missing_forecast_values_preserve_prior_cache_values_and_timestamps():
    fetched_at = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    previous = {
        "forecast_rain_1h_mm": 4.0,
        "forecast_fetched_at_1h": fetched_at.isoformat(),
        "observed_humidity_pct": 70.0,
    }

    merged, updated = _merge_weather_cache(
        previous,
        {"forecast_rain_1h_mm": None, "forecast_rain_3h_mm": 0.0},
        {"observed_humidity_pct": None, "observed_rainfall_1h_mm": 0.0},
        fetched_at.replace(minute=5),
    )

    assert merged["forecast_rain_1h_mm"] == 4.0
    assert merged["forecast_fetched_at_1h"] == fetched_at.isoformat()
    assert merged["forecast_rain_3h_mm"] == 0.0
    assert merged["observed_humidity_pct"] == 70.0
    assert merged["observed_rainfall_1h_mm"] == 0.0
    assert updated is True


def test_cache_freshness_uses_each_horizon_timestamp():
    now = datetime.now(timezone.utc)
    cache = {
        "forecast_rain_1h_mm": 1.0,
        "forecast_fetched_at_1h": (now - timedelta(minutes=16)).isoformat(),
        "forecast_rain_3h_mm": 3.0,
        "forecast_fetched_at_3h": (now - timedelta(minutes=2)).isoformat(),
    }

    assert _has_fresh_cached_forecast(cache, now)
    cache["forecast_fetched_at_3h"] = (now - timedelta(minutes=16)).isoformat()
    assert not _has_fresh_cached_forecast(cache, now)


def test_weather_ingestion_skips_when_another_run_holds_redis_lock(monkeypatch):
    class BusyRedis:
        def __init__(self):
            self.set_call = None

        async def set(self, *args, **kwargs):
            self.set_call = (args, kwargs)
            return None

    async def run():
        service = WeatherIngestService()
        client = BusyRedis()

        async def get_redis():
            return client

        monkeypatch.setattr(service, "get_redis", get_redis)
        result = await service.ingest_all_wards()
        return result, client.set_call

    result, set_call = asyncio.run(run())

    assert result == {"status": "skipped", "reason": "ingestion_already_running"}
    assert set_call[1]["nx"] is True
    assert set_call[1]["ex"] == 90


def test_weather_only_beat_schedule_does_not_dispatch_shared_jobs():
    from backend.tasks.weather_beat_app import weather_beat_app

    schedule = weather_beat_app.conf.beat_schedule

    assert len(schedule) == 2
    ingest_entry = schedule["ingest-weather-every-10-min"]
    assert ingest_entry["schedule"] == 600.0
    assert ingest_entry["options"]["queue"] == "weather_ingest"
    assert ingest_entry["task"] == "backend.tasks.scheduled_tasks.task_ingest_weather_all_wards"

    risk_entry = schedule["compute-ward-risk-scores-every-15-min"]
    assert risk_entry["schedule"] == 900.0
    assert risk_entry["options"]["queue"] == "weather_ingest"
    assert risk_entry["task"] == "backend.tasks.scheduled_tasks.task_compute_all_ward_risk_scores"

    # Verify no social or shared jobs are present
    assert not any("social" in k.lower() for k in schedule)


def test_predictive_cache_checks_freshness_per_horizon():
    now = datetime.now(timezone.utc)
    cache_payload = {
        "fetched_at": now.isoformat(),
        "forecast_rain_1h_mm": 1.0,
        "forecast_fetched_at_1h": now.isoformat(),
        "forecast_rain_3h_mm": 5.0,
        "forecast_fetched_at_3h": (now - timedelta(minutes=20)).isoformat(),
    }

    class ForecastRedis:
        async def ping(self):
            return True

        async def get(self, _key):
            return json.dumps(cache_payload)

    async def run():
        service = PredictiveFeatureService(None, redis_client=ForecastRedis())
        return await service._forecast_cache(["BMC-A"], now)

    forecasts, error = asyncio.run(run())

    assert error is None
    assert forecasts["BMC-A"]["forecast_rainfall_1h_mm"] == 1.0
    assert forecasts["BMC-A"]["forecast_rainfall_3h_mm"] is None
    assert forecasts["BMC-A"]["forecast_rainfall_6h_mm"] is None


def test_existing_rainfall_coverage_has_24_ward_codes_and_is_only_provenance():
    coverage = load_rainfall_coverage()
    hourly_distances = [
        details["nearest_hourly_station"]["distance_km"]
        for details in coverage.values()
        if "nearest_hourly_station" in details
    ]

    assert len(coverage) == 24
    assert len(hourly_distances) == 24
    assert min(hourly_distances) >= 13.0
    assert max(hourly_distances) > 40.0


def test_outlook_category_thresholds_are_explicit():
    assert classify_outlook_score(0.249) == "low"
    assert classify_outlook_score(0.25) == "moderate"
    assert classify_outlook_score(0.5) == "high"
    assert classify_outlook_score(0.75) == "critical"
