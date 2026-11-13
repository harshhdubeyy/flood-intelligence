"""Run the weather-only Beat scheduler under a renewable Redis singleton lease."""

import asyncio
import hashlib
import json
import logging
import os
import signal
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, NamedTuple, Optional, Tuple

import redis.asyncio as redis
from redis.exceptions import RedisError
from celery.beat import Service

from backend.config import get_settings
from backend.tasks.weather_beat_app import weather_beat_app

logger = logging.getLogger("fip.weather_beat")
LOCK_KEY = "fip:weather:scheduler:lock"
HEARTBEAT_KEY = "fip:weather:scheduler:heartbeat"
LEASE_SECONDS = 60
RENEW_INTERVAL_SECONDS = 20
RENEW_RETRY_SECONDS = 2
LEASE_SAFETY_MARGIN_SECONDS = 10
REDIS_COMMAND_TIMEOUT_SECONDS = 5
SERVICE_MAX_INTERVAL_SECONDS = 5
SERVICE_HEALTH_POLL_SECONDS = 1

ACQUIRE_LEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[2])
    return 1
end
if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[2]) then
    redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[2])
    return 1
end
return 0
"""

RENEW_LEASE_SCRIPT = """
local owner = redis.call('GET', KEYS[1])
if not owner then
    return {-1, -2, -2, ''}
end
local ttl_before = redis.call('PTTL', KEYS[1])
if owner ~= ARGV[1] then
    return {0, ttl_before, ttl_before, redis.sha1hex(owner)}
end
redis.call('EXPIRE', KEYS[1], ARGV[2])
redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[2])
return {1, ttl_before, redis.call('PTTL', KEYS[1]), redis.sha1hex(owner)}
"""

RELEASE_LEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call('DEL', KEYS[1])
local heartbeat = redis.call('GET', KEYS[2])
if heartbeat then
    local ok, value = pcall(cjson.decode, heartbeat)
    if ok and value['instance_id'] == ARGV[1] then
        redis.call('DEL', KEYS[2])
    end
end
return 1
"""

RedisRetryableErrors = (RedisError, OSError, asyncio.TimeoutError)


class LeaseRenewalResult(NamedTuple):
    renewed: bool
    outcome: str
    ttl_before_ms: int
    ttl_after_ms: int
    observed_owner_fingerprint: Optional[str]


class WeatherBeatService(Service):
    """Celery Beat service with an explicit cross-thread stop hook."""

    def request_stop(self) -> None:
        self._is_shutdown.set()


def _heartbeat_payload(token: str) -> str:
    return json.dumps(
        {
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
            "instance_id": token,
        }
    )


async def _acquire_lease(client: Any, token: str) -> bool:
    acquired = await asyncio.wait_for(
        client.eval(
            ACQUIRE_LEASE_SCRIPT,
            2,
            LOCK_KEY,
            HEARTBEAT_KEY,
            token,
            LEASE_SECONDS,
            _heartbeat_payload(token),
        ),
        timeout=REDIS_COMMAND_TIMEOUT_SECONDS,
    )
    return acquired == 1


async def _renew_lease(client: Any, token: str) -> LeaseRenewalResult:
    result = await client.eval(
        RENEW_LEASE_SCRIPT,
        2,
        LOCK_KEY,
        HEARTBEAT_KEY,
        token,
        LEASE_SECONDS,
        _heartbeat_payload(token),
    )
    status_code, ttl_before_ms, ttl_after_ms, owner_fingerprint = result
    outcome = {
        1: "renewed",
        0: "owner_mismatch",
        -1: "lease_missing",
    }.get(status_code, "unexpected_result")
    return LeaseRenewalResult(
        renewed=status_code == 1,
        outcome=outcome,
        ttl_before_ms=ttl_before_ms,
        ttl_after_ms=ttl_after_ms,
        observed_owner_fingerprint=owner_fingerprint or None,
    )


async def _renew_with_retry(
    client: Any,
    token: str,
    last_confirmed_at: float,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    command_timeout: float = REDIS_COMMAND_TIMEOUT_SECONDS,
) -> Tuple[bool, float]:
    lease_deadline = last_confirmed_at + LEASE_SECONDS
    attempt = 0
    owner_fingerprint = hashlib.sha1(token.encode("ascii")).hexdigest()[:12]
    while True:
        attempt += 1
        remaining = lease_deadline - clock()
        retry_budget = remaining - LEASE_SAFETY_MARGIN_SECONDS
        if retry_budget <= 0:
            logger.error(
                "event=lease_renewal_deadline_exhausted pid=%s "
                "owner_fingerprint=%s attempt=%s lease_remaining_seconds=%.2f",
                os.getpid(),
                owner_fingerprint,
                attempt,
                max(0, remaining),
            )
            return False, last_confirmed_at

        try:
            result = await asyncio.wait_for(
                _renew_lease(client, token),
                timeout=min(command_timeout, retry_budget),
            )
        except RedisRetryableErrors as exc:
            logger.warning(
                "event=lease_renewal_retry pid=%s owner_fingerprint=%s "
                "attempt=%s error_type=%s lease_remaining_seconds=%.2f",
                os.getpid(),
                owner_fingerprint,
                attempt,
                type(exc).__name__,
                max(0, lease_deadline - clock()),
            )
            retry_budget = lease_deadline - clock() - LEASE_SAFETY_MARGIN_SECONDS
            if retry_budget <= 0:
                continue
            await sleep(min(RENEW_RETRY_SECONDS, retry_budget))
            continue

        elapsed_since_renewal = max(0, clock() - last_confirmed_at)
        if not result.renewed:
            logger.error(
                "event=lease_ownership_lost pid=%s owner_fingerprint=%s "
                "attempt=%s renewal_outcome=%s expected_owner_fingerprint=%s "
                "observed_owner_fingerprint=%s observed_ttl_before_ms=%s "
                "elapsed_since_last_renewal_seconds=%.3f action=stop_beat",
                os.getpid(),
                owner_fingerprint,
                attempt,
                result.outcome,
                owner_fingerprint,
                result.observed_owner_fingerprint or "none",
                result.ttl_before_ms,
                elapsed_since_renewal,
            )
            return False, last_confirmed_at

        confirmed_at = clock()
        logger.info(
            "event=lease_renewed pid=%s owner_fingerprint=%s attempt=%s "
            "ttl_before_ms=%s ttl_after_ms=%s elapsed_since_last_renewal_seconds=%.3f",
            os.getpid(),
            owner_fingerprint,
            attempt,
            result.ttl_before_ms,
            result.ttl_after_ms,
            elapsed_since_renewal,
        )
        return True, confirmed_at


async def _release_lease(client: Any, token: str) -> bool:
    released = await asyncio.wait_for(
        client.eval(
            RELEASE_LEASE_SCRIPT,
            2,
            LOCK_KEY,
            HEARTBEAT_KEY,
            token,
        ),
        timeout=REDIS_COMMAND_TIMEOUT_SECONDS,
    )
    return released == 1


async def _wait_or_stop(stop_event: asyncio.Event, timeout: float) -> bool:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return False
    return True


async def run() -> int:
    settings = get_settings()
    client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=REDIS_COMMAND_TIMEOUT_SECONDS,
        socket_timeout=REDIS_COMMAND_TIMEOUT_SECONDS,
        health_check_interval=15,
    )
    token = uuid.uuid4().hex
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop_event.set)

    acquired = False
    service = None
    beat_task = None
    service_stopped = True
    exit_code = 0
    last_confirmed_at = 0.0
    shutdown_reason = "signal"
    owner_fingerprint = hashlib.sha1(token.encode("ascii")).hexdigest()[:12]
    try:
        while not stop_event.is_set():
            try:
                acquired = await _acquire_lease(client, token)
            except RedisRetryableErrors as exc:
                logger.warning(
                    "event=lease_acquisition_retry error_type=%s",
                    type(exc).__name__,
                )
                await _wait_or_stop(stop_event, RENEW_RETRY_SECONDS)
                continue
            if acquired:
                last_confirmed_at = time.monotonic()
                logger.info(
                    "event=lease_acquired pid=%s owner_fingerprint=%s ttl_seconds=%s",
                    os.getpid(),
                    owner_fingerprint,
                    LEASE_SECONDS,
                )
                break
            logger.warning("event=lease_acquisition_busy retry_seconds=%s", RENEW_RETRY_SECONDS)
            await _wait_or_stop(stop_event, RENEW_RETRY_SECONDS)

        if not acquired:
            logger.info("event=beat_shutdown reason=signal_before_lease")
            return 0

        service = WeatherBeatService(
            app=weather_beat_app,
            max_interval=SERVICE_MAX_INTERVAL_SECONDS,
            schedule_filename="/tmp/fip-weather-beat-schedule",
        )
        beat_task = asyncio.create_task(asyncio.to_thread(service.start))
        service_stopped = False
        logger.info(
            "event=beat_started pid=%s queue=weather_ingest",
            os.getpid(),
        )

        next_renewal_at = last_confirmed_at + RENEW_INTERVAL_SECONDS
        while not stop_event.is_set():
            wait_seconds = min(
                max(0, next_renewal_at - time.monotonic()),
                SERVICE_HEALTH_POLL_SECONDS,
            )
            if await _wait_or_stop(stop_event, wait_seconds):
                break
            if beat_task.done():
                try:
                    await beat_task
                except Exception:
                    logger.exception("event=beat_service_exited reason=exception")
                    exit_code = 1
                    shutdown_reason = "beat_service_exception"
                else:
                    logger.error("event=beat_service_exited reason=unexpected_return")
                    exit_code = 1
                    shutdown_reason = "beat_service_unexpected_return"
                service_stopped = True
                break

            if time.monotonic() < next_renewal_at:
                continue

            renewed, confirmed_at = await _renew_with_retry(
                client,
                token,
                last_confirmed_at,
            )
            if not renewed:
                exit_code = 1
                shutdown_reason = "lease_ownership_lost"
                break
            last_confirmed_at = confirmed_at
            next_renewal_at = confirmed_at + RENEW_INTERVAL_SECONDS

        logger.info(
            "event=beat_shutdown pid=%s owner_fingerprint=%s reason=%s",
            os.getpid(),
            owner_fingerprint,
            shutdown_reason,
        )
        return exit_code
    finally:
        if service is not None:
            service.request_stop()
            if beat_task is not None and not beat_task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(beat_task),
                        timeout=10,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "event=beat_service_shutdown_timeout "
                        "action=retain_lease_until_ttl"
                    )
                except Exception:
                    logger.exception("event=beat_service_shutdown_failed")
                service_stopped = beat_task.done()
        if acquired and service_stopped:
            try:
                released = await _release_lease(client, token)
                logger.info(
                    "event=lease_released pid=%s owner_fingerprint=%s ownership_matched=%s",
                    os.getpid(),
                    owner_fingerprint,
                    released,
                )
            except RedisRetryableErrors as exc:
                logger.warning(
                    "event=lease_release_deferred_to_ttl error_type=%s",
                    type(exc).__name__,
                )
        elif acquired:
            logger.error(
                "event=lease_release_skipped reason=beat_service_still_running"
            )
        try:
            await client.aclose()
        except RedisRetryableErrors as exc:
            logger.warning(
                "event=redis_client_close_failed error_type=%s",
                type(exc).__name__,
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(run()))
