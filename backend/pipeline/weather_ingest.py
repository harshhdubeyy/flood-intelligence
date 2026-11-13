"""
Weather ingestion worker pipeline for OpenWeatherMap and Open-Meteo.
Polls spatial coordinates across Mumbai wards, updates Redis caches,
and persists snapshots to PostgreSQL/PostGIS.
"""

import logging
import asyncio
import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
import httpx
from sqlalchemy import select, func
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from backend.config import get_settings
from backend.models.database import async_session_factory
from backend.models.ward import Ward
from backend.models.weather import WeatherSnapshot

logger = logging.getLogger("fip.weather_ingest")
settings = get_settings()

# Default Mumbai centroid fallback coordinates
MUMBAI_FALLBACK_LAT = 19.0760
MUMBAI_FALLBACK_LON = 72.8777
FORECAST_HORIZONS = (1, 3, 6, 12, 24)
FORECAST_CACHE_TTL_SECONDS = 900
INGESTION_LOCK_KEY = "fip:weather:ingestion:lock"
INGESTION_LOCK_TTL_SECONDS = 90
INGESTION_STATUS_KEY = "fip:weather:ingestion:status"


def _merge_weather_cache(
    previous: Dict[str, Any],
    forecast_rain: Dict[str, Optional[float]],
    observations: Dict[str, Optional[float]],
    fetched_at: datetime,
) -> tuple[Dict[str, Any], bool]:
    """Keep prior values when a provider omits a field; timestamp each forecast horizon."""
    payload = dict(previous)
    timestamp = fetched_at.astimezone(timezone.utc).isoformat()
    has_new_forecast = False

    for hours in FORECAST_HORIZONS:
        key = f"forecast_rain_{hours}h_mm"
        value = forecast_rain.get(key)
        if value is not None:
            payload[key] = value
            payload[f"forecast_fetched_at_{hours}h"] = timestamp
            has_new_forecast = True

    for key, value in observations.items():
        if value is not None:
            payload[key] = value

    if has_new_forecast:
        payload["fetched_at"] = timestamp
    return payload, has_new_forecast


def _has_fresh_cached_forecast(payload: Dict[str, Any], now: datetime) -> bool:
    has_horizon_timestamps = any(
        payload.get(f"forecast_fetched_at_{hours}h") for hours in FORECAST_HORIZONS
    )
    for hours in FORECAST_HORIZONS:
        value = payload.get(f"forecast_rain_{hours}h_mm")
        timestamp = payload.get(f"forecast_fetched_at_{hours}h")
        if not has_horizon_timestamps:
            timestamp = payload.get("fetched_at")
        if value is None or not isinstance(timestamp, str):
            continue
        try:
            fetched_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age = now.astimezone(timezone.utc) - fetched_at.astimezone(timezone.utc)
        if timedelta(minutes=-5) <= age <= timedelta(seconds=FORECAST_CACHE_TTL_SECONDS):
            return True
    return False


def _forecast_accumulation(
    values: List[Any],
    hours: int,
    timestamps: Optional[List[str]] = None,
    now: Optional[datetime] = None,
) -> Optional[float]:
    """Sum a complete forward forecast window; missing intervals are not zero."""
    start_index = 0
    if timestamps is not None and now is not None:
        local_now = now.astimezone(ZoneInfo("Asia/Kolkata"))
        current_hour = local_now.replace(minute=0, second=0, microsecond=0)
        parsed_times = []
        for timestamp in timestamps:
            try:
                parsed = datetime.fromisoformat(timestamp)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            parsed_times.append(parsed)
        start_index = next(
            (index for index, timestamp in enumerate(parsed_times) if timestamp >= current_hour),
            len(parsed_times),
        )
        selected_times = parsed_times[start_index:start_index + hours]
        if (
            len(selected_times) != hours
            or any(
                selected_times[index] - selected_times[index - 1] != timedelta(hours=1)
                for index in range(1, len(selected_times))
            )
        ):
            return None

    if len(values) < start_index + hours:
        return None
    window = values[start_index:start_index + hours]
    try:
        amounts = [float(value) for value in window]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) and value >= 0 for value in amounts):
        return None
    return round(sum(amounts), 2)


class WeatherIngestService:
    """
    Ingests live meteorological data from OpenWeatherMap & Open-Meteo APIs,
    computes rainfall accumulations (1h, 3h, 24h), and caches results in Redis.
    """

    def __init__(self):
        self.settings = settings
        self._redis: Optional[aioredis.Redis] = None

    async def get_redis(self) -> Optional[aioredis.Redis]:
        """Lazy-initialize async Redis client."""
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(
                    self.settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed ({e}); proceeding without Redis cache.")
                self._redis = None
        return self._redis

    async def close_redis(self) -> None:
        if self._redis is not None:
            redis_client = self._redis
            self._redis = None
            await redis_client.aclose()

    async def fetch_open_meteo_forecast(
        self,
        client: httpx.AsyncClient,
        lat: float,
        lon: float
    ) -> Dict[str, Any]:
        """
        Fetch high-resolution hourly precipitation data from Open-Meteo (No API key required).
        """
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&"
            f"hourly=precipitation,rain,wind_speed_10m,relative_humidity_2m&"
            f"forecast_days=2&timezone=Asia%2FKolkata"
        )
        for attempt in range(3):
            try:
                resp = await client.get(url, timeout=12.0)
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        logger.warning("Open-Meteo returned invalid JSON for (%s, %s): %s", lat, lon, exc)
                        return {}

                if (resp.status_code == 429 or resp.status_code >= 500) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.warning(
                    "Open-Meteo returned status %s for (%s, %s): %s",
                    resp.status_code,
                    lat,
                    lon,
                    resp.text[:100],
                )
                return {}
            except httpx.RequestError as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.warning("Open-Meteo network query failed for (%s, %s): %s", lat, lon, exc)
                return {}

        return {}

    async def fetch_openweathermap_current(
        self,
        client: httpx.AsyncClient,
        lat: float,
        lon: float
    ) -> Optional[Dict[str, Any]]:
        """
        Query OpenWeatherMap current weather endpoint for rainfall rate and humidity.
        Falls back to None if API key is unconfigured or call fails.
        """
        api_key = self.settings.openweathermap_api_key
        if not api_key:
            return None

        url = (
            f"https://api.openweathermap.org/data/2.5/weather?"
            f"lat={lat}&lon={lon}&appid={api_key}&units=metric"
        )
        for attempt in range(3):
            try:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        logger.warning("OpenWeatherMap returned invalid JSON: %s", exc)
                        return None

                if (resp.status_code == 429 or resp.status_code >= 500) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.warning(
                    "OpenWeatherMap returned status %s: %s",
                    resp.status_code,
                    resp.text[:100],
                )
                return None
            except httpx.RequestError as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.warning("OpenWeatherMap request failed: %s", exc)
                return None

        return None

    def estimate_tide_height(self, is_coastal: bool) -> Optional[float]:
        """
        Calculate Mumbai coastal Arabian Sea tide height in meters.
        Follows semi-diurnal tidal harmonic model calibrated to Mumbai Apollo Bunder (0.5m to 4.8m).
        """
        if not is_coastal:
            return None

        now = datetime.now(timezone.utc)
        # 12.42-hour lunar semi-diurnal tidal cycle
        hours_fraction = (now.hour * 3600 + now.minute * 60 + now.second) / 3600.0
        import math
        phase = (hours_fraction % 12.42) / 12.42 * 2 * math.pi
        # Mean sea level ~2.5m, oscillating between 0.8m and 4.3m
        tide_height = 2.55 + 1.65 * math.sin(phase)
        return round(float(tide_height), 2)

    async def ingest_all_wards(self) -> Dict[str, Any]:
        r = await self.get_redis()
        if r is None:
            raise RuntimeError("Redis is required to coordinate and cache weather ingestion.")

        lock_token = uuid.uuid4().hex
        acquired = await r.set(
            INGESTION_LOCK_KEY,
            lock_token,
            nx=True,
            ex=INGESTION_LOCK_TTL_SECONDS,
        )
        if not acquired:
            logger.info("Weather ingestion skipped because another run holds the Redis lock.")
            return {"status": "skipped", "reason": "ingestion_already_running"}

        started_at = datetime.now(timezone.utc)
        lock_lost = asyncio.Event()
        renewal_task = asyncio.create_task(self._renew_ingestion_lock(r, lock_token, lock_lost))
        ingestion_task = None
        lost_task = None
        try:
            await self._update_ingestion_status(
                r,
                {
                    "last_started_at": started_at.isoformat(),
                    "last_status": "running",
                    "latest_errors": [],
                },
            )
            ingestion_task = asyncio.create_task(self._ingest_all_wards(r))
            lost_task = asyncio.create_task(lock_lost.wait())
            done, _ = await asyncio.wait(
                (ingestion_task, lost_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if lost_task in done and lock_lost.is_set():
                ingestion_task.cancel()
                await asyncio.gather(ingestion_task, return_exceptions=True)
                raise RuntimeError("Weather ingestion lease was lost; run cancelled to prevent overlap.")
            lost_task.cancel()
            result = await ingestion_task
            completed_at = datetime.now(timezone.utc)
            latest_errors = [
                *result.get("forecast_errors", []),
                *[
                    {"ward_id": ward_id, "message": "Redis forecast cache could not be updated."}
                    for ward_id in result.get("cache_errors", [])
                ],
            ]
            status_update: Dict[str, Any] = {
                "last_completed_at": completed_at.isoformat(),
                "last_status": result["status"],
                "wards_total": result.get("wards_updated", 0),
                "wards_with_fresh_forecasts": result.get("cache_available_wards", 0),
                "latest_errors": latest_errors,
            }
            if result["status"] == "success":
                status_update["last_success_at"] = completed_at.isoformat()
            await self._update_ingestion_status(r, status_update)
            logger.info(
                "Weather ingestion %s at %s: %s/%s wards with forecasts",
                result["status"],
                completed_at.isoformat(),
                result.get("forecast_available_wards", 0),
                result.get("wards_updated", 0),
            )
            return {**result, "started_at": started_at.isoformat(), "completed_at": completed_at.isoformat()}
        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            try:
                await self._update_ingestion_status(
                    r,
                    {
                        "last_completed_at": completed_at.isoformat(),
                        "last_status": "failed",
                        "latest_errors": [{"message": f"Ingestion failed: {type(exc).__name__}"}],
                    },
                )
            except Exception:
                logger.exception("Could not persist weather ingestion failure status.")
            logger.exception("Weather ingestion failed.")
            raise
        finally:
            if lost_task is not None:
                lost_task.cancel()
                await asyncio.gather(lost_task, return_exceptions=True)
            renewal_task.cancel()
            await asyncio.gather(renewal_task, return_exceptions=True)
            try:
                await r.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                    1,
                    INGESTION_LOCK_KEY,
                    lock_token,
                )
            except Exception:
                logger.exception("Could not release the weather ingestion lease.")

    async def _renew_ingestion_lock(
        self,
        redis_client: aioredis.Redis,
        lock_token: str,
        lock_lost: asyncio.Event,
    ) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                renewed = await redis_client.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end",
                    1,
                    INGESTION_LOCK_KEY,
                    lock_token,
                    INGESTION_LOCK_TTL_SECONDS,
                )
            except Exception:
                logger.exception("Weather ingestion lease renewal failed.")
                lock_lost.set()
                return
            if renewed != 1:
                logger.error("Weather ingestion lease ownership was lost.")
                lock_lost.set()
                return

    async def _update_ingestion_status(
        self,
        redis_client: aioredis.Redis,
        updates: Dict[str, Any],
    ) -> None:
        raw = await redis_client.get(INGESTION_STATUS_KEY)
        status_data: Dict[str, Any] = {}
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    status_data = parsed
            except json.JSONDecodeError:
                logger.warning("Replacing malformed weather ingestion status cache.")
        status_data.update(updates)
        await redis_client.set(INGESTION_STATUS_KEY, json.dumps(status_data))

    async def _ingest_all_wards(self, r: aioredis.Redis) -> Dict[str, Any]:
        """
        Execute full batch ingestion across all administrative wards in Mumbai:
        1. Queries ward centroid geometries via PostGIS ST_Centroid
        2. Retrieves live weather (Open-Meteo + OpenWeatherMap)
        3. Separates observed rainfall from forecast precipitation
        4. Saves snapshots to database and updates Redis cache
        """
        async with async_session_factory() as session:
            # Query wards with centroid coordinates in EPSG:4326
            stmt = select(
                Ward.ward_id,
                Ward.ward_name,
                Ward.is_coastal,
                func.ST_X(func.ST_Centroid(Ward.geom)).label("lon"),
                func.ST_Y(func.ST_Centroid(Ward.geom)).label("lat")
            )
            res = await session.execute(stmt)
            ward_rows = res.all()

            if not ward_rows:
                logger.warning("No wards found in database to ingest weather for.")
                return {"status": "skipped", "wards_updated": 0, "snapshots": 0}

            snapshots_created = 0
            forecast_unavailable_wards = []
            forecast_errors = []
            cache_errors = []
            fresh_cache_wards: set[str] = set()

            async with httpx.AsyncClient() as client:
                semaphore = asyncio.Semaphore(6)

                async def fetch_ward_data(row: Any) -> tuple[Any, Dict[str, Any], Dict[str, Optional[float]], Optional[Dict[str, Any]]]:
                    lat = float(row.lat) if row.lat is not None else MUMBAI_FALLBACK_LAT
                    lon = float(row.lon) if row.lon is not None else MUMBAI_FALLBACK_LON
                    async with semaphore:
                        meteo_data = await self.fetch_open_meteo_forecast(client, lat, lon)
                        hourly = meteo_data.get("hourly", {})
                        rain_series: List[float] = hourly.get("precipitation") or hourly.get("rain") or []
                        forecast_times: List[str] = hourly.get("time") or []
                        forecast_time = datetime.now(timezone.utc)
                        forecast_rain = {
                            f"forecast_rain_{hours}h_mm": _forecast_accumulation(
                                rain_series, hours, forecast_times, forecast_time
                            )
                            for hours in FORECAST_HORIZONS
                        }
                        owm_data = await self.fetch_openweathermap_current(client, lat, lon)
                    return row, meteo_data, forecast_rain, owm_data

                ward_data = await asyncio.gather(*(fetch_ward_data(row) for row in ward_rows))
                for row, meteo_data, forecast_rain, owm_data in ward_data:
                    is_coastal = bool(row.is_coastal)
                    missing_horizons = [
                        hours
                        for hours in FORECAST_HORIZONS
                        if forecast_rain.get(f"forecast_rain_{hours}h_mm") is None
                    ]
                    if missing_horizons:
                        forecast_errors.append(
                            {
                                "ward_id": row.ward_id,
                                "message": "Forecast missing one or more complete horizons.",
                                "missing_horizons": [f"{hours}h" for hours in missing_horizons],
                            }
                        )
                    if len(missing_horizons) == len(FORECAST_HORIZONS):
                        forecast_unavailable_wards.append(row.ward_id)

                    # Only use OpenWeatherMap's current observation for observed rainfall.
                    observed_rain_1h = None
                    observed_wind_kmh = None
                    observed_humidity = None

                    if owm_data:
                        rain_obj = owm_data.get("rain") or {}
                        if rain_obj.get("1h") is not None:
                            observed_rain_1h = float(rain_obj["1h"])

                        wind = owm_data.get("wind") or {}
                        if wind.get("speed") is not None:
                            observed_wind_kmh = float(wind["speed"]) * 3.6

                        main = owm_data.get("main") or {}
                        if main.get("humidity") is not None:
                            observed_humidity = float(main["humidity"])

                    # Tide is still an estimate, not a measured observation.
                    tide_m = self.estimate_tide_height(is_coastal)

                    source = (
                                "owm+open-meteo"
                                if owm_data and meteo_data
                                else "owm-current"
                                if owm_data
                                else "open-meteo"
                                if meteo_data
                                else "unavailable"
                            )

                    snapshot = WeatherSnapshot(
                        ward_id=row.ward_id,
                        source=source,
                        rainfall_1h_mm=(
                            round(observed_rain_1h, 2)
                            if observed_rain_1h is not None else None
                        ),
                        rainfall_3h_mm=None,
                        rainfall_24h_mm=None,
                        wind_speed_kmh=(
                            round(observed_wind_kmh, 1)
                            if observed_wind_kmh is not None else None
                        ),
                        humidity_pct=(
                            round(observed_humidity, 1)
                            if observed_humidity is not None else None
                        ),
                        tide_height_m=tide_m,
                        fetched_at=datetime.now(timezone.utc)
                    )

                    session.add(snapshot)
                    snapshots_created += 1

                    # Update Redis live cache with 15-min TTL
                    cache_key = f"fip:weather:latest:{row.ward_id}"
                    try:
                        raw_cache = await r.get(cache_key)
                    except RedisError:
                        cache_errors.append(row.ward_id)
                        logger.exception("Could not read forecast cache for ward %s.", row.ward_id)
                        continue
                    previous_cache: Dict[str, Any] = {}
                    if raw_cache:
                        try:
                            previous_cache = json.loads(raw_cache)
                        except json.JSONDecodeError:
                            logger.warning("Replacing malformed weather cache for ward %s.", row.ward_id)
                    cache_payload, _ = _merge_weather_cache(
                        previous_cache,
                        forecast_rain,
                        {
                            "observed_rainfall_1h_mm": observed_rain_1h,
                            "observed_wind_speed_kmh": observed_wind_kmh,
                            "observed_humidity_pct": observed_humidity,
                            "tide_height_m": tide_m,
                        },
                        datetime.now(timezone.utc),
                    )
                    cache_payload["tide_source"] = "simulated_harmonic_estimate"
                    try:
                        await r.setex(
                            cache_key,
                            FORECAST_CACHE_TTL_SECONDS,
                            json.dumps(cache_payload),
                        )
                        if _has_fresh_cached_forecast(cache_payload, datetime.now(timezone.utc)):
                            fresh_cache_wards.add(row.ward_id)
                    except RedisError:
                        cache_errors.append(row.ward_id)
                        logger.exception("Could not write forecast cache for ward %s.", row.ward_id)

                await session.commit()

            logger.info(f"Weather ingestion complete: {snapshots_created} snapshots saved.")
            partial = bool(forecast_errors or cache_errors)
            return {
                "status": "partial" if partial else "success",
                "wards_updated": len(ward_rows),
                "snapshots_created": snapshots_created,
                "forecast_available_wards": len(ward_rows) - len(forecast_unavailable_wards),
                "cache_available_wards": len(fresh_cache_wards),
                "forecast_unavailable_wards": forecast_unavailable_wards,
                "forecast_errors": forecast_errors,
                "cache_errors": cache_errors,
            }


weather_ingest_service = WeatherIngestService()
