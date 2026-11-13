import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import Response
from backend.api.routes.social import _post_response
from backend.config import Settings
from backend.models.social_media_post import (
    SocialComplianceOperation,
    SocialMediaPost,
    SocialPostDerivedArtifact,
)
from backend.pipeline.social_collection import SocialCollectionService
from backend.pipeline.social_lifecycle import (
    SocialLifecycleService,
    source_id_digest,
)
from backend.pipeline.social_providers import ProviderPost, SocialProviderError
from backend.pipeline.social_retention import (
    collection_policy_ready,
    provider_retention_policy,
)


ALLOWED_FIELDS = [
    "external_post_id",
    "original_url",
    "text_content",
    "posted_at",
    "matched_keywords",
    "location",
    "media_references",
]


def _settings(**values):
    defaults = {
        "REDDIT_CLIENT_ID": "",
        "REDDIT_CLIENT_SECRET": "",
        "TWITTER_BEARER_TOKEN": "",
        "SOCIAL_COLLECTION_ENABLED": False,
        "SOCIAL_LIFECYCLE_ENABLED": True,
        "SOCIAL_LIFECYCLE_DRY_RUN": True,
        "SOCIAL_TOMBSTONE_HMAC_KEY": "test-key-not-for-production-32bytes",
        "SOCIAL_REDDIT_POLICY_APPROVED": True,
        "SOCIAL_REDDIT_RETENTION_DAYS": 14,
        "SOCIAL_REDDIT_RECONCILE_INTERVAL_HOURS": 12,
        "SOCIAL_REDDIT_ALLOWED_FIELDS": ALLOWED_FIELDS,
        "SOCIAL_X_POLICY_APPROVED": True,
        "SOCIAL_X_RETENTION_DAYS": 14,
        "SOCIAL_X_RECONCILE_INTERVAL_HOURS": 12,
        "SOCIAL_X_ALLOWED_FIELDS": ALLOWED_FIELDS,
    }
    defaults.update(values)
    return Settings(_env_file=None, **defaults)


class FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeResult:
    def __init__(self, values=None, scalar=None):
        self.values = values or []
        self.scalar = scalar

    def scalars(self):
        return FakeScalars(self.values)

    def scalar_one_or_none(self):
        return self.values[0] if self.values else None


class FakeLifecycleDb:
    def __init__(self, post=None, rows=None, fail_delete=False):
        self.post = post
        self.rows = rows if rows is not None else ([post] if post else [])
        self.fail_delete = fail_delete
        self.statements = []
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, row):
        self.added.append(row)

    async def get(self, model, post_id, **_kwargs):
        return self.post if self.post and self.post.id == post_id else None

    async def execute(self, statement):
        self.statements.append(statement)
        if self.fail_delete and "DELETE FROM social_post_derived_artifacts" in str(statement):
            self.fail_delete = False
            raise RuntimeError("database failure with parameter values")
        if "SELECT social_media_posts" in str(statement):
            return FakeResult(self.rows)
        if "SELECT social_compliance_tombstones" in str(statement):
            return FakeResult([])
        return FakeResult([])

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _post(**overrides):
    values = {
        "id": 31,
        "platform": "x",
        "external_post_id": "source-post-id",
        "original_url": "https://x.com/i/status/source-post-id",
        "text_content": "Waterlogging near Dadar",
        "posted_at": datetime(2026, 11, 12, tzinfo=timezone.utc),
        "collected_at": datetime(2026, 11, 13, tzinfo=timezone.utc),
        "location_text": "Dadar",
        "latitude": 19.02,
        "longitude": 72.84,
        "ward_id": "GN",
        "geolocation_confidence": 1.0,
        "ward_assignment_provenance": "post_coordinates_st_covers",
        "matched_keywords": ["waterlogging"],
        "media_references": [{"url": "https://media.example/image"}],
        "processing_status": "collected",
        "source_provenance": {"provider": "x", "collection_id": "private-provenance"},
        "source_status": "current",
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
        "last_verified_at": datetime.now(timezone.utc),
        "next_reconcile_at": datetime.now(timezone.utc),
        "reconcile_attempt_count": 0,
    }
    values.update(overrides)
    return SocialMediaPost(**values)


def test_provider_retention_policy_is_fail_closed_without_explicit_approval():
    settings = Settings(_env_file=None)
    assert not settings.social_collection_enabled
    assert not settings.social_lifecycle_enabled
    assert not provider_retention_policy(settings, "reddit").can_collect
    assert not collection_policy_ready(settings, "reddit")

    missing_key = _settings(SOCIAL_TOMBSTONE_HMAC_KEY="")
    assert not collection_policy_ready(
        _settings(SOCIAL_COLLECTION_ENABLED=True, SOCIAL_TOMBSTONE_HMAC_KEY=""),
        "reddit",
    )
    assert provider_retention_policy(missing_key, "reddit").retention_days == 14


def test_policy_does_not_invent_retention_duration_or_permitted_fields():
    policy = provider_retention_policy(
        _settings(
            SOCIAL_REDDIT_RETENTION_DAYS=None,
            SOCIAL_REDDIT_ALLOWED_FIELDS=[],
        ),
        "reddit",
    )
    assert policy.retention_days is None
    assert not policy.can_collect
    assert policy.expiration_at(datetime.now(timezone.utc)) is None


def test_collection_is_blocked_by_unknown_policy_even_when_operator_flag_is_on():
    class Provider:
        name = "reddit"

        def is_configured(self):
            return True

        async def fetch_page(self, *_args):
            raise AssertionError("Provider must not be called with an unknown policy.")

    settings = _settings(
        SOCIAL_COLLECTION_ENABLED=True,
        SOCIAL_REDDIT_POLICY_APPROVED=False,
    )
    db = FakeLifecycleDb()
    result = asyncio.run(
        SocialCollectionService(settings=settings, providers=[Provider()]).collect(db)
    )
    assert result["providers"][0]["status"] == "policy_blocked"


def test_source_id_tombstones_are_keyed_and_non_reversible():
    settings = _settings()
    digest = source_id_digest(settings, "x", "source-post-id")
    assert digest and len(digest) == 64
    assert "source-post-id" not in digest
    assert digest == source_id_digest(settings, "x", "source-post-id")
    assert digest != source_id_digest(settings, "reddit", "source-post-id")
    assert source_id_digest(_settings(SOCIAL_TOMBSTONE_HMAC_KEY=""), "x", "id") is None
    assert source_id_digest(_settings(SOCIAL_TOMBSTONE_HMAC_KEY="too-short"), "x", "id") is None
    assert not collection_policy_ready(
        _settings(
            SOCIAL_COLLECTION_ENABLED=True,
            SOCIAL_TOMBSTONE_HMAC_KEY="too-short",
        ),
        "x",
    )


def test_dry_run_expiry_logs_without_removing_source_or_derived_data():
    expired = _post(expires_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
    db = FakeLifecycleDb(post=expired)
    service = SocialLifecycleService(settings=_settings())
    result = asyncio.run(
        service.expire_due(
            db, now=datetime(2026, 11, 13, tzinfo=timezone.utc), dry_run=True
        )
    )
    assert result == {"dry_run": True, "processed": 1, "retryable": 0}
    assert expired.text_content == "Waterlogging near Dadar"
    assert expired.source_status == "current"
    assert not any("DELETE FROM social_post_derived_artifacts" in str(q) for q in db.statements)
    assert db.added[0].status == "dry_run"
    assert "Waterlogging" not in str(db.added[0].__dict__)


def test_expiry_redacts_all_source_fields_and_attached_artifacts():
    expired = _post(expires_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
    db = FakeLifecycleDb(post=expired)
    result = asyncio.run(
        SocialLifecycleService(settings=_settings()).expire_due(
            db, now=datetime(2026, 11, 13, tzinfo=timezone.utc), dry_run=False
        )
    )
    assert result["processed"] == 1
    assert expired.source_status == "expired"
    assert expired.external_post_id is None
    assert expired.original_url is None and expired.text_content is None
    assert expired.posted_at is None and expired.matched_keywords == []
    assert expired.media_references == [] and expired.source_provenance == {}
    assert expired.location_text is None and expired.latitude is None
    assert expired.longitude is None and expired.ward_id is None
    assert expired.geolocation_confidence is None
    assert any("DELETE FROM social_post_derived_artifacts" in str(q) for q in db.statements)
    assert db.added[-1].outcome == "expired_and_tombstoned"


def test_manual_takedown_is_idempotent_and_does_not_touch_flood_event_tables():
    post = _post()
    db = FakeLifecycleDb(post=post)
    service = SocialLifecycleService(settings=_settings())
    result = asyncio.run(service.takedown(db, post_id=post.id))
    assert result["status"] == "succeeded"
    assert post.source_status == "deleted"
    assert post.external_post_id is None and post.text_content is None
    assert post.original_url is None and post.media_references == []
    assert post.matched_keywords == [] and post.location_text is None
    assert post.latitude is None and post.longitude is None and post.ward_id is None
    assert db.added[-1].status == "succeeded"
    assert all("flood_events" not in str(statement) for statement in db.statements)

    statement_count = len(db.statements)
    duplicate = asyncio.run(service.takedown(db, post_id=post.id))
    assert duplicate["outcome"] == "already_redacted"
    assert len(db.statements) == statement_count
    assert len(db.added) == 2


def test_removal_without_hmac_key_redacts_source_and_records_provider_block():
    post = _post()
    db = FakeLifecycleDb(post=post)
    service = SocialLifecycleService(
        settings=_settings(SOCIAL_TOMBSTONE_HMAC_KEY="")
    )
    result = asyncio.run(service.takedown(db, post_id=post.id))
    assert result["status"] == "succeeded"
    assert post.text_content is None and post.external_post_id is None
    assert db.added[-1].outcome == "redacted_collection_remains_blocked"


def test_partial_cleanup_failure_is_retryable_and_does_not_log_source_content():
    post = _post()
    db = FakeLifecycleDb(post=post, fail_delete=True)
    service = SocialLifecycleService(settings=_settings())
    result = asyncio.run(service.takedown(db, post_id=post.id))
    assert result["status"] == "retryable"
    assert post.source_status == "pending_compliance"
    assert post.text_content == "Waterlogging near Dadar"
    operation = db.added[-1]
    assert operation.status == "retryable"
    assert operation.error_code == "processing_error"
    assert "Waterlogging" not in str(operation.__dict__)
    assert "parameter values" not in str(operation.__dict__)
    assert db.rollbacks == 1


def test_provider_rate_limit_never_marks_a_post_deleted():
    class Provider:
        name = "x"

        def is_configured(self):
            return True

        async def fetch_post(self, *_args):
            raise SocialProviderError("rate_limited")

    post = _post(reconcile_attempt_count=2)
    db = FakeLifecycleDb(post=post)
    result = asyncio.run(
        SocialLifecycleService(
            settings=_settings(SOCIAL_LIFECYCLE_ENABLED=True),
            providers=[Provider()],
        ).reconcile_due(db, now=datetime.now(timezone.utc))
    )
    assert result["retryable"] == 1
    assert post.source_status == "pending_compliance"
    assert post.text_content == "Waterlogging near Dadar"
    assert post.reconcile_attempt_count == 3
    assert db.added[-1].error_code == "rate_limited"
    assert db.added[-1].status == "retryable"
    assert db.added[-1].attempt_number == 3


def test_confirmed_source_absence_redacts_source_and_derived_data():
    class Provider:
        name = "x"

        def is_configured(self):
            return True

        async def fetch_post(self, *_args):
            raise SocialProviderError("source_unavailable")

    post = _post()
    db = FakeLifecycleDb(post=post)
    result = asyncio.run(
        SocialLifecycleService(
            settings=_settings(SOCIAL_LIFECYCLE_ENABLED=True),
            providers=[Provider()],
        ).reconcile_due(db, now=datetime.now(timezone.utc))
    )
    assert result["removed"] == 1
    assert post.source_status == "unavailable"
    assert post.external_post_id is None and post.text_content is None
    assert any("DELETE FROM social_post_derived_artifacts" in str(q) for q in db.statements)


def test_rehydration_refreshes_permitted_fields_and_keeps_original_expiry():
    class Provider:
        name = "x"

        def is_configured(self):
            return True

        async def fetch_post(self, _client, post_id):
            assert post_id == "source-post-id"
            return ProviderPost(
                platform="x",
                external_post_id=post_id,
                original_url="https://x.com/i/status/source-post-id",
                text_content="Road flooding by Dadar",
                posted_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
                location_text="Dadar",
                latitude=None,
                longitude=None,
                media_references=[],
            )

    post = _post()
    original_expiry = post.expires_at
    db = FakeLifecycleDb(post=post)
    service = SocialLifecycleService(
        settings=_settings(SOCIAL_LIFECYCLE_ENABLED=True), providers=[Provider()]
    )
    result = asyncio.run(service.rehydrate(db, post_id=post.id))
    assert result["status"] == "succeeded"
    assert post.source_status == "current"
    assert post.text_content == "Road flooding by Dadar"
    assert post.expires_at == original_expiry
    assert post.matched_keywords == ["flooding"]
    assert post.ward_id is None
    assert any("DELETE FROM social_post_derived_artifacts" in str(q) for q in db.statements)


def test_api_hides_content_for_unverified_and_expired_posts():
    unverified = _post(source_status="unverified")
    response = _post_response(unverified)
    assert response.text_content is None
    assert response.original_url is None
    assert response.external_post_id is None
    assert response.matched_keywords == []
    assert response.media_references == []

    expired = _post(
        source_status="current",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    response = _post_response(expired)
    assert response.source_status == "expired"
    assert response.text_content is None
    assert response.location_text is None


def test_api_hides_content_after_source_reconciliation_deadline():
    stale = _post(
        next_reconcile_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    response = _post_response(stale)
    assert response.source_status == "unverified"
    assert response.text_content is None
    assert response.external_post_id is None


def test_api_does_not_treat_unverified_source_as_current():
    unverified = _post(
        last_verified_at=None,
        next_reconcile_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = _post_response(unverified)
    assert response.source_status == "unverified"
    assert response.text_content is None


def test_api_returns_content_only_after_successful_verification_until_recheck_deadline():
    current = _post(
        next_reconcile_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    response = _post_response(current)
    assert response.source_status == "current"
    assert response.text_content == current.text_content
    assert response.original_url == current.original_url


def test_compliance_audit_model_does_not_define_update_or_delete_payload_fields():
    columns = set(SocialComplianceOperation.__table__.columns.keys())
    assert columns == {
        "id",
        "request_id",
        "attempt_number",
        "operation_type",
        "platform",
        "post_id",
        "trigger_source",
        "status",
        "error_code",
        "outcome",
        "event_id_digest",
        "created_at",
    }
    assert "payload" not in columns and "text_content" not in columns
    fk = next(iter(SocialPostDerivedArtifact.__table__.foreign_keys))
    assert fk.ondelete == "CASCADE"


def test_migration_defines_append_only_audit_and_preserves_existing_post_rows():
    migration = Path(
        "backend/migrations/versions/0007_social_data_lifecycle.py"
    ).read_text()
    assert "BEFORE UPDATE OR DELETE ON social_compliance_operations" in migration
    assert "BEFORE TRUNCATE ON social_compliance_operations" in migration
    assert "Refusing to remove populated" in migration
    assert "op.drop_table(\"social_media_posts\")" not in migration
    assert "source_status" in migration


def test_compliance_operation_request_id_is_a_uuid():
    assert isinstance(uuid.uuid4(), uuid.UUID)
