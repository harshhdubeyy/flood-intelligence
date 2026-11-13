import asyncio
import hashlib
import json
import logging

from redis.exceptions import ConnectionError

from backend.tasks.weather_beat import (
    ACQUIRE_LEASE_SCRIPT,
    HEARTBEAT_KEY,
    LOCK_KEY,
    RELEASE_LEASE_SCRIPT,
    RENEW_LEASE_SCRIPT,
    LEASE_SECONDS,
    RENEW_RETRY_SECONDS,
    _acquire_lease,
    _release_lease,
    _renew_lease,
    _renew_with_retry,
    WeatherBeatService,
)
from backend.tasks.weather_beat_app import weather_beat_app


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    async def eval(self, script, key_count, *args):
        assert key_count == 2
        lock_key, heartbeat_key = args[:2]
        if script == ACQUIRE_LEASE_SCRIPT:
            token, ttl, heartbeat = args[2:]
            if self.values.get(lock_key) == token:
                self.values[heartbeat_key] = heartbeat
                self.ttls[lock_key] = ttl
                self.ttls[heartbeat_key] = ttl
                return 1
            if lock_key in self.values:
                return 0
            self.values[lock_key] = token
            self.values[heartbeat_key] = heartbeat
            self.ttls[lock_key] = ttl
            self.ttls[heartbeat_key] = ttl
            return 1
        if script == RENEW_LEASE_SCRIPT:
            token, ttl, heartbeat = args[2:]
            owner = self.values.get(lock_key)
            if owner is None:
                return [-1, -2, -2, ""]
            if owner != token:
                return [0, self.ttls.get(lock_key, 0) * 1000,
                        self.ttls.get(lock_key, 0) * 1000,
                        hashlib.sha1(owner.encode("ascii")).hexdigest()]
            ttl_before = self.ttls.get(lock_key, 0) * 1000
            self.values[heartbeat_key] = heartbeat
            self.ttls[lock_key] = ttl
            self.ttls[heartbeat_key] = ttl
            return [1, ttl_before, ttl * 1000, hashlib.sha1(token.encode("ascii")).hexdigest()]
        if script == RELEASE_LEASE_SCRIPT:
            (token,) = args[2:]
            if self.values.get(lock_key) != token:
                return 0
            del self.values[lock_key]
            try:
                heartbeat = json.loads(self.values[heartbeat_key])
            except (KeyError, json.JSONDecodeError):
                heartbeat = {}
            if heartbeat.get("instance_id") == token:
                self.values.pop(heartbeat_key, None)
            self.ttls.pop(lock_key, None)
            self.ttls.pop(heartbeat_key, None)
            return 1
        raise AssertionError("Unexpected Redis script.")


def test_lease_acquire_renew_and_release_are_owner_checked():
    async def run():
        client = FakeRedis()
        assert await _acquire_lease(client, "owner-a")
        assert not await _acquire_lease(client, "owner-b")
        wrong_owner_result = await _renew_lease(client, "owner-b")
        assert not wrong_owner_result.renewed
        assert wrong_owner_result.outcome == "owner_mismatch"
        assert wrong_owner_result.observed_owner_fingerprint == hashlib.sha1(
            b"owner-a"
        ).hexdigest()
        owner_result = await _renew_lease(client, "owner-a")
        assert owner_result.renewed
        assert owner_result.outcome == "renewed"
        assert owner_result.ttl_after_ms == LEASE_SECONDS * 1000

        client.values[LOCK_KEY] = "owner-b"
        client.values[HEARTBEAT_KEY] = json.dumps({"instance_id": "owner-b"})
        assert not await _release_lease(client, "owner-a")
        assert client.values[LOCK_KEY] == "owner-b"
        assert await _release_lease(client, "owner-b")
        assert LOCK_KEY not in client.values
        assert HEARTBEAT_KEY not in client.values

    asyncio.run(run())


def test_renewal_retries_transient_redis_error_before_lease_safety_deadline():
    class FlakyRedis:
        def __init__(self):
            self.calls = 0

        async def eval(self, *_args):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("temporary failure")
            return [1, 25_000, LEASE_SECONDS * 1000, hashlib.sha1(b"owner").hexdigest()]

    async def run():
        client = FlakyRedis()
        clock_value = [100.0]

        async def fake_sleep(seconds):
            clock_value[0] += seconds

        renewed, confirmed_at = await _renew_with_retry(
            client,
            "owner",
            100.0,
            clock=lambda: clock_value[0],
            sleep=fake_sleep,
        )
        return client, renewed, confirmed_at, clock_value[0]

    client, renewed, confirmed_at, clock_value = asyncio.run(run())
    assert renewed
    assert client.calls == 2
    assert clock_value == 100.0 + RENEW_RETRY_SECONDS
    assert confirmed_at == clock_value


def test_renewal_stops_before_unconfirmed_lease_can_expire():
    class UnavailableRedis:
        def __init__(self):
            self.calls = 0

        async def eval(self, *_args):
            self.calls += 1
            raise ConnectionError("temporary outage")

    async def run():
        client = UnavailableRedis()
        clock_value = [0.0]

        async def fake_sleep(seconds):
            clock_value[0] += seconds

        renewed, last_confirmed_at = await _renew_with_retry(
            client,
            "owner",
            0.0,
            clock=lambda: clock_value[0],
            sleep=fake_sleep,
        )
        return client, renewed, last_confirmed_at, clock_value[0]

    client, renewed, confirmed_at, clock_value = asyncio.run(run())
    assert not renewed
    assert confirmed_at == 0.0
    assert clock_value == LEASE_SECONDS - 10
    assert client.calls > 1


def test_renewal_stops_immediately_when_another_owner_holds_lease():
    class ReplacedLeaseRedis:
        async def eval(self, *_args):
            return [0, 40_000, 40_000, hashlib.sha1(b"new-owner").hexdigest()]

    async def run():
        clock_value = [0.0]

        async def unexpected_sleep(_seconds):
            raise AssertionError("Renewal should not retry after ownership is lost.")

        return await _renew_with_retry(
            ReplacedLeaseRedis(),
            "stale-owner",
            0.0,
            clock=lambda: clock_value[0],
            sleep=unexpected_sleep,
        )

    renewed, last_confirmed_at = asyncio.run(run())
    assert not renewed
    assert last_confirmed_at == 0.0


def test_renewal_reports_expired_lease_separately_from_owner_mismatch(caplog):
    class ExpiredLeaseRedis:
        async def eval(self, *_args):
            return [-1, -2, -2, ""]

    async def run():
        return await _renew_with_retry(ExpiredLeaseRedis(), "owner-secret-token", 10.0)

    with caplog.at_level(logging.ERROR, logger="fip.weather_beat"):
        renewed, confirmed_at = asyncio.run(run())
    assert not renewed
    assert confirmed_at == 10.0
    assert "renewal_outcome=lease_missing" in caplog.text
    assert "observed_ttl_before_ms=-2" in caplog.text
    assert "owner-secret-token" not in caplog.text


def test_concurrent_acquisition_allows_only_one_lease_owner():
    async def run():
        client = FakeRedis()
        results = await asyncio.gather(
            *(_acquire_lease(client, f"owner-{index}") for index in range(20))
        )
        return results, client.values[LOCK_KEY]

    results, owner = asyncio.run(run())
    assert sum(results) == 1
    assert owner in {f"owner-{index}" for index in range(20)}


def test_renewal_timeout_retries_and_recovers_after_redis_reconnect():
    class ReconnectingRedis:
        def __init__(self):
            self.calls = 0

        async def eval(self, *_args):
            self.calls += 1
            if self.calls == 1:
                await asyncio.Future()
            return [1, 25_000, LEASE_SECONDS * 1000, hashlib.sha1(b"owner").hexdigest()]

    async def run():
        client = ReconnectingRedis()
        clock_value = [100.0]

        async def fake_sleep(seconds):
            clock_value[0] += seconds

        result = await _renew_with_retry(
            client,
            "owner",
            100.0,
            clock=lambda: clock_value[0],
            sleep=fake_sleep,
            command_timeout=0.01,
        )
        return client, result

    client, (renewed, confirmed_at) = asyncio.run(run())
    assert renewed
    assert client.calls == 2
    assert confirmed_at == 100.0 + RENEW_RETRY_SECONDS


def test_renewal_diagnostics_distinguish_replaced_owner():
    client = FakeRedis()
    asyncio.run(_acquire_lease(client, "current-owner"))
    client.values[LOCK_KEY] = "replacement-owner"
    client.ttls[LOCK_KEY] = 37

    result = asyncio.run(_renew_lease(client, "current-owner"))
    assert not result.renewed
    assert result.outcome == "owner_mismatch"
    assert result.ttl_before_ms == 37_000
    assert result.observed_owner_fingerprint == hashlib.sha1(
        b"replacement-owner"
    ).hexdigest()


def test_shutdown_cancellation_while_renewal_is_pending_does_not_release_owner():
    class PendingRedis(FakeRedis):
        async def eval(self, script, key_count, *args):
            if script == ACQUIRE_LEASE_SCRIPT:
                return await super().eval(script, key_count, *args)
            if script == RENEW_LEASE_SCRIPT:
                await asyncio.Future()
            return await super().eval(script, key_count, *args)

    async def run():
        client = PendingRedis()
        assert await _acquire_lease(client, "owner-a")
        renewal = asyncio.create_task(_renew_with_retry(client, "owner-a", 100.0))
        await asyncio.sleep(0)
        renewal.cancel()
        try:
            await renewal
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Expected pending renewal to be cancelled on shutdown.")
        return client

    client = asyncio.run(run())
    assert client.values[LOCK_KEY] == "owner-a"
    assert asyncio.run(_acquire_lease(client, "owner-b")) is False


def test_beat_service_has_explicit_stop_hook_for_same_process_lifecycle():
    service = WeatherBeatService(
        app=weather_beat_app,
        max_interval=5,
        schedule_filename="/tmp/weather-beat-test-schedule",
    )
    assert not service._is_shutdown.is_set()

    service.request_stop()

    assert service._is_shutdown.is_set()
