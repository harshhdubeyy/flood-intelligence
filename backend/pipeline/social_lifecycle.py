"""Fail-closed retention, deletion, takedown, and source reconciliation."""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.models.social_media_post import (
    SocialComplianceOperation,
    SocialComplianceTombstone,
    SocialMediaPost,
    SocialPostDerivedArtifact,
)
from backend.pipeline.social_providers import (
    ProviderPost,
    SocialProvider,
    SocialProviderError,
    build_social_providers,
    match_flood_keywords,
)
from backend.pipeline.social_retention import provider_retention_policy

logger = logging.getLogger("fip.social.lifecycle")
MAX_RECONCILE_ATTEMPTS = 5
MAX_LIFECYCLE_BATCH = 200
SAFE_PROVIDER_ERROR_CODES = {
    "access_denied",
    "authentication_rejected",
    "invalid_response",
    "network_error",
    "provider_unavailable",
    "rate_limited",
    "source_unavailable",
    "timeout",
}


def source_id_digest(settings: Settings, platform: str, external_post_id: str) -> Optional[str]:
    key = settings.social_tombstone_hmac_key.encode("utf-8")
    if len(key) < 32:
        return None
    message = f"{platform}\0{external_post_id}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def event_id_digest(event_id: Optional[str]) -> Optional[str]:
    if not event_id:
        return None
    return hashlib.sha256(event_id.encode("utf-8")).hexdigest()


def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, SocialProviderError) and exc.code in SAFE_PROVIDER_ERROR_CODES:
        return exc.code
    return "processing_error"


def _append_operation(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    attempt_number: int,
    operation_type: str,
    platform: str,
    post_id: Optional[int],
    trigger_source: str,
    status: str,
    outcome: str,
    error_code: Optional[str] = None,
    event_id_hash: Optional[str] = None,
) -> None:
    db.add(
        SocialComplianceOperation(
            request_id=request_id,
            attempt_number=attempt_number,
            operation_type=operation_type,
            platform=platform,
            post_id=post_id,
            trigger_source=trigger_source,
            status=status,
            outcome=outcome,
            error_code=error_code,
            event_id_digest=event_id_hash,
        )
    )


async def _write_tombstone(
    db: AsyncSession,
    settings: Settings,
    platform: str,
    external_post_id: Optional[str],
) -> bool:
    digest = (
        source_id_digest(settings, platform, external_post_id)
        if external_post_id
        else None
    )
    if digest is None:
        return False
    await db.execute(
        pg_insert(SocialComplianceTombstone)
        .values(platform=platform, source_id_digest=digest)
        .on_conflict_do_nothing(
            constraint="uq_social_tombstone_platform_digest"
        )
    )
    return True


async def _redact_source(
    db: AsyncSession,
    settings: Settings,
    post: SocialMediaPost,
    *,
    source_status: str,
    now: datetime,
) -> bool:
    external_post_id = post.external_post_id
    await db.execute(
        delete(SocialPostDerivedArtifact).where(
            SocialPostDerivedArtifact.social_post_id == post.id
        )
    )
    tombstone_written = await _write_tombstone(
        db, settings, post.platform, external_post_id
    )
    post.external_post_id = None
    post.original_url = None
    post.text_content = None
    post.posted_at = None
    post.location_text = None
    post.latitude = None
    post.longitude = None
    post.ward_id = None
    post.geolocation_confidence = None
    post.ward_assignment_provenance = None
    post.matched_keywords = []
    post.media_references = []
    post.source_provenance = {}
    post.source_status = source_status
    post.expires_at = None
    post.last_verified_at = None
    post.next_reconcile_at = None
    post.reconcile_attempt_count = 0
    post.updated_at = now
    return tombstone_written


class SocialLifecycleService:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        providers: Optional[Sequence[SocialProvider]] = None,
    ):
        self.settings = settings or get_settings()
        self.providers = list(
            providers if providers is not None else build_social_providers(self.settings)
        )
        self.providers_by_name = {provider.name: provider for provider in self.providers}

    async def expire_due(
        self,
        db: AsyncSession,
        *,
        now: Optional[datetime] = None,
        dry_run: Optional[bool] = None,
        limit: int = MAX_LIFECYCLE_BATCH,
    ) -> dict[str, int | bool]:
        current_time = now or datetime.now(timezone.utc)
        preview = self.settings.social_lifecycle_dry_run if dry_run is None else dry_run
        bounded_limit = max(1, min(limit, MAX_LIFECYCLE_BATCH))
        posts = (
            await db.execute(
                select(SocialMediaPost)
                .where(
                    SocialMediaPost.expires_at.is_not(None),
                    SocialMediaPost.expires_at <= current_time,
                    SocialMediaPost.source_status.not_in(("deleted", "expired")),
                )
                .order_by(SocialMediaPost.expires_at)
                .limit(bounded_limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        processed = 0
        retryable = 0
        for post in posts:
            request_id = uuid.uuid4()
            post_id = post.id
            platform = post.platform
            try:
                if preview:
                    _append_operation(
                        db,
                        request_id=request_id,
                        attempt_number=1,
                        operation_type="retention_expiry",
                        platform=platform,
                        post_id=post_id,
                        trigger_source="scheduled_expiry",
                        status="dry_run",
                        outcome="would_expire",
                    )
                else:
                    tombstone_written = await _redact_source(
                        db,
                        self.settings,
                        post,
                        source_status="expired",
                        now=current_time,
                    )
                    _append_operation(
                        db,
                        request_id=request_id,
                        attempt_number=1,
                        operation_type="retention_expiry",
                        platform=platform,
                        post_id=post_id,
                        trigger_source="scheduled_expiry",
                        status="succeeded",
                        outcome=(
                            "expired_and_tombstoned"
                            if tombstone_written
                            else "expired_collection_remains_blocked"
                        ),
                    )
                await db.commit()
                processed += 1
            except Exception:
                await db.rollback()
                retryable += 1
                _append_operation(
                    db,
                    request_id=request_id,
                    attempt_number=1,
                    operation_type="retention_expiry",
                    platform=platform,
                    post_id=post_id,
                    trigger_source="scheduled_expiry",
                    status="retryable",
                    outcome="redaction_failed",
                    error_code="processing_error",
                )
                await db.commit()
                logger.warning(
                    "Social retention expiry failed",
                    extra={"platform": platform, "error_code": "processing_error"},
                )
        return {"dry_run": preview, "processed": processed, "retryable": retryable}

    async def takedown(
        self,
        db: AsyncSession,
        *,
        post_id: int,
        trigger_source: str = "operator_takedown",
        request_id: Optional[uuid.UUID] = None,
        attempt_number: int = 1,
        event_id: Optional[str] = None,
        target_status: str = "deleted",
    ) -> dict[str, str | int]:
        operation_id = request_id or uuid.uuid4()
        post: Optional[SocialMediaPost] = None
        try:
            post = await db.get(SocialMediaPost, post_id, with_for_update=True)
            if post is None:
                raise LookupError("social_post_not_found")
            if post.source_status in {"deleted", "expired", "unavailable"}:
                _append_operation(
                    db,
                    request_id=operation_id,
                    attempt_number=attempt_number,
                    operation_type="source_deletion",
                    platform=post.platform,
                    post_id=post.id,
                    trigger_source=trigger_source,
                    status="succeeded",
                    outcome="already_redacted",
                    event_id_hash=event_id_digest(event_id),
                )
                await db.commit()
                return {"status": "succeeded", "outcome": "already_redacted"}
            post.source_status = "pending_compliance"
            tombstone_written = await _redact_source(
                db,
                self.settings,
                post,
                source_status=target_status,
                now=datetime.now(timezone.utc),
            )
            _append_operation(
                db,
                request_id=operation_id,
                attempt_number=attempt_number,
                operation_type="source_deletion",
                platform=post.platform,
                post_id=post.id,
                trigger_source=trigger_source,
                status="succeeded",
                outcome=(
                    "redacted_and_tombstoned"
                    if tombstone_written
                    else "redacted_collection_remains_blocked"
                ),
                event_id_hash=event_id_digest(event_id),
            )
            await db.commit()
            logger.info(
                "Social source content redacted",
                extra={
                    "platform": post.platform,
                    "post_id": post.id,
                    "outcome": "redacted",
                },
            )
            return {"status": "succeeded", "outcome": "redacted"}
        except LookupError:
            await db.rollback()
            raise
        except Exception as exc:
            await db.rollback()
            post = await db.get(SocialMediaPost, post_id, with_for_update=True)
            platform = post.platform if post else "unknown"
            if post:
                post.source_status = "pending_compliance"
                post.reconcile_attempt_count += 1
                post.next_reconcile_at = datetime.now(timezone.utc) + timedelta(
                    minutes=min(2**attempt_number, 60)
                )
            error_code = _safe_error_code(exc)
            _append_operation(
                db,
                request_id=operation_id,
                attempt_number=attempt_number,
                operation_type="source_deletion",
                platform=platform,
                post_id=post_id if post else None,
                trigger_source=trigger_source,
                status="retryable",
                outcome="redaction_failed",
                error_code=error_code,
                event_id_hash=event_id_digest(event_id),
            )
            await db.commit()
            logger.warning(
                "Social source deletion is retryable",
                extra={"platform": platform, "error_code": error_code},
            )
            return {"status": "retryable", "outcome": error_code}

    async def handle_provider_event(
        self,
        db: AsyncSession,
        *,
        platform: str,
        external_post_id: str,
        action: str,
        event_id: Optional[str] = None,
    ) -> dict[str, str]:
        if platform not in {"reddit", "x"}:
            raise ValueError("Unsupported social provider.")
        if action in {"delete", "remove"}:
            post = (
                await db.execute(
                    select(SocialMediaPost)
                    .where(
                        SocialMediaPost.platform == platform,
                        SocialMediaPost.external_post_id == external_post_id,
                    )
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if post is None:
                digest = source_id_digest(
                    self.settings, platform, external_post_id
                )
                if digest:
                    await _write_tombstone(
                        db, self.settings, platform, external_post_id
                    )
                request_id = uuid.uuid4()
                _append_operation(
                    db,
                    request_id=request_id,
                    attempt_number=1,
                    operation_type="source_deletion",
                    platform=platform,
                    post_id=None,
                    trigger_source="provider_notification",
                    status="succeeded",
                    outcome=(
                        "source_not_locally_present"
                        if digest
                        else "source_not_locally_present_collection_remains_blocked"
                    ),
                    event_id_hash=event_id_digest(event_id),
                )
                await db.commit()
                return {"status": "succeeded", "outcome": "source_not_locally_present"}
            return await self.takedown(
                db,
                post_id=post.id,
                trigger_source="provider_notification",
                event_id=event_id,
            )
        if action in {"drop", "withheld"}:
            post = await self._find_source(db, platform, external_post_id)
            if post is None:
                return {"status": "not_found", "outcome": "source_not_locally_present"}
            return await self.takedown(
                db,
                post_id=post.id,
                trigger_source="provider_notification",
                event_id=event_id,
                target_status="unavailable",
            )
        if action == "scrub_geo":
            post = await self._find_source(db, platform, external_post_id)
            if post is None:
                return {"status": "not_found", "outcome": "source_not_locally_present"}
            return await self.scrub_location(
                db, post_id=post.id, event_id=event_id
            )
        if action in {"rehydrate", "tweet_edit", "undrop"}:
            post = await self._find_source(db, platform, external_post_id)
            if post is None:
                return {"status": "not_found", "outcome": "source_not_locally_present"}
            return await self.rehydrate(
                db, post_id=post.id, event_id=event_id
            )
        raise ValueError("Unsupported provider compliance action.")

    async def scrub_location(
        self,
        db: AsyncSession,
        *,
        post_id: int,
        event_id: Optional[str] = None,
    ) -> dict[str, str]:
        post = await db.get(SocialMediaPost, post_id, with_for_update=True)
        if post is None:
            raise LookupError("social_post_not_found")
        post.location_text = None
        post.latitude = None
        post.longitude = None
        post.ward_id = None
        post.geolocation_confidence = None
        post.ward_assignment_provenance = None
        await db.execute(
            delete(SocialPostDerivedArtifact).where(
                SocialPostDerivedArtifact.social_post_id == post.id
            )
        )
        _append_operation(
            db,
            request_id=uuid.uuid4(),
            attempt_number=1,
            operation_type="scrub_geo",
            platform=post.platform,
            post_id=post.id,
            trigger_source="provider_notification",
            status="succeeded",
            outcome="location_and_derived_artifacts_removed",
            event_id_hash=event_id_digest(event_id),
        )
        await db.commit()
        return {"status": "succeeded", "outcome": "location_and_derived_artifacts_removed"}

    async def rehydrate(
        self,
        db: AsyncSession,
        *,
        post_id: int,
        event_id: Optional[str] = None,
    ) -> dict[str, str]:
        post = await db.get(SocialMediaPost, post_id, with_for_update=True)
        if post is None or not post.external_post_id:
            raise LookupError("social_post_not_found")
        provider = self.providers_by_name.get(post.platform)
        policy = provider_retention_policy(self.settings, post.platform)
        if (
            not self.settings.social_lifecycle_enabled
            or not policy.can_collect
            or not provider
            or not provider.is_configured()
        ):
            post.source_status = "pending_compliance"
            post.next_reconcile_at = None
            _append_operation(
                db,
                request_id=uuid.uuid4(),
                attempt_number=1,
                operation_type="rehydrate",
                platform=post.platform,
                post_id=post.id,
                trigger_source="provider_notification",
                status="retryable",
                outcome="provider_policy_or_access_unavailable",
                error_code="policy_unavailable",
                event_id_hash=event_id_digest(event_id),
            )
            await db.commit()
            return {"status": "retryable", "outcome": "policy_unavailable"}
        request_id = uuid.uuid4()
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                current = await provider.fetch_post(client, post.external_post_id)
            await self._refresh_source(db, post, current, policy.allowed_fields)
            post.source_status = "current"
            post.last_verified_at = datetime.now(timezone.utc)
            post.reconcile_attempt_count = 0
            post.next_reconcile_at = post.last_verified_at + timedelta(
                hours=policy.reconcile_interval_hours or 1
            )
            _append_operation(
                db,
                request_id=request_id,
                attempt_number=1,
                operation_type="rehydrate",
                platform=post.platform,
                post_id=post.id,
                trigger_source="provider_notification",
                status="succeeded",
                outcome="source_refreshed",
                event_id_hash=event_id_digest(event_id),
            )
            await db.commit()
            return {"status": "succeeded", "outcome": "source_refreshed"}
        except Exception as exc:
            if (
                isinstance(exc, SocialProviderError)
                and exc.code == "source_unavailable"
            ):
                tombstone_written = await _redact_source(
                    db,
                    self.settings,
                    post,
                    source_status="unavailable",
                    now=datetime.now(timezone.utc),
                )
                _append_operation(
                    db,
                    request_id=request_id,
                    attempt_number=1,
                    operation_type="rehydrate",
                    platform=post.platform,
                    post_id=post.id,
                    trigger_source="provider_notification",
                    status="succeeded",
                    outcome=(
                        "source_unavailable_and_redacted"
                        if tombstone_written
                        else "source_unavailable_redacted_collection_blocked"
                    ),
                    event_id_hash=event_id_digest(event_id),
                )
                await db.commit()
                return {"status": "succeeded", "outcome": "source_unavailable"}
            await db.rollback()
            post = await db.get(SocialMediaPost, post_id, with_for_update=True)
            if post:
                post.source_status = "pending_compliance"
                post.reconcile_attempt_count += 1
                post.next_reconcile_at = self._retry_at(post.reconcile_attempt_count)
            error_code = _safe_error_code(exc)
            _append_operation(
                db,
                request_id=request_id,
                attempt_number=1,
                operation_type="rehydrate",
                platform=post.platform if post else "unknown",
                post_id=post_id if post else None,
                trigger_source="provider_notification",
                status=(
                    "retryable"
                    if post and post.reconcile_attempt_count < MAX_RECONCILE_ATTEMPTS
                    else "failed"
                ),
                outcome="source_refresh_failed",
                error_code=error_code,
                event_id_hash=event_id_digest(event_id),
            )
            await db.commit()
            return {"status": "retryable", "outcome": error_code}

    async def reconcile_due(
        self, db: AsyncSession, *, now: Optional[datetime] = None, limit: int = 50
    ) -> dict[str, int]:
        if not self.settings.social_lifecycle_enabled:
            return {"verified": 0, "removed": 0, "retryable": 0}
        current_time = now or datetime.now(timezone.utc)
        rows = (
            await db.execute(
                select(SocialMediaPost)
                .where(
                    SocialMediaPost.source_status.in_(
                        ("unverified", "current", "pending_compliance")
                    ),
                    SocialMediaPost.external_post_id.is_not(None),
                    SocialMediaPost.next_reconcile_at <= current_time,
                    SocialMediaPost.reconcile_attempt_count < MAX_RECONCILE_ATTEMPTS,
                )
                .order_by(SocialMediaPost.next_reconcile_at)
                .limit(max(1, min(limit, MAX_LIFECYCLE_BATCH)))
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        current = 0
        removed = 0
        retryable = 0
        for post in rows:
            provider = self.providers_by_name.get(post.platform)
            policy = provider_retention_policy(self.settings, post.platform)
            request_id = uuid.uuid4()
            attempt_number = post.reconcile_attempt_count + 1
            if (
                not self.settings.social_lifecycle_enabled
                or not policy.can_collect
                or not provider
                or not provider.is_configured()
            ):
                post.source_status = "pending_compliance"
                post.next_reconcile_at = None
                _append_operation(
                    db,
                    request_id=request_id,
                    attempt_number=attempt_number,
                    operation_type="source_reconciliation",
                    platform=post.platform,
                    post_id=post.id,
                    trigger_source="scheduled_reconciliation",
                    status="retryable",
                    outcome="provider_policy_or_access_unavailable",
                    error_code="policy_unavailable",
                )
                await db.commit()
                retryable += 1
                continue
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    current_source = await provider.fetch_post(
                        client, post.external_post_id
                    )
                await self._refresh_source(
                    db, post, current_source, policy.allowed_fields
                )
                post.source_status = "current"
                post.last_verified_at = current_time
                post.reconcile_attempt_count = 0
                post.next_reconcile_at = current_time + timedelta(
                    hours=policy.reconcile_interval_hours or 1
                )
                _append_operation(
                    db,
                    request_id=request_id,
                    attempt_number=attempt_number,
                    operation_type="source_reconciliation",
                    platform=post.platform,
                    post_id=post.id,
                    trigger_source="scheduled_reconciliation",
                    status="succeeded",
                    outcome="source_verified_and_refreshed",
                )
                await db.commit()
                current += 1
            except SocialProviderError as exc:
                if exc.code == "source_unavailable":
                    await _redact_source(
                        db,
                        self.settings,
                        post,
                        source_status="unavailable",
                        now=current_time,
                    )
                    _append_operation(
                        db,
                        request_id=request_id,
                        attempt_number=attempt_number,
                        operation_type="source_reconciliation",
                        platform=post.platform,
                        post_id=post.id,
                        trigger_source="scheduled_reconciliation",
                        status="succeeded",
                        outcome="source_unavailable_and_redacted",
                    )
                    await db.commit()
                    removed += 1
                    continue
                await self._record_reconcile_failure(
                    db, post, request_id, attempt_number, exc, current_time
                )
                retryable += 1
            except Exception as exc:
                await self._record_reconcile_failure(
                    db, post, request_id, attempt_number, exc, current_time
                )
                retryable += 1
        return {"verified": current, "removed": removed, "retryable": retryable}

    async def retry_takedowns(
        self, db: AsyncSession, *, limit: int = 50
    ) -> dict[str, int]:
        latest_attempts = (
            select(
                SocialComplianceOperation.request_id,
                func.max(SocialComplianceOperation.attempt_number).label("attempt_number"),
            )
            .group_by(SocialComplianceOperation.request_id)
            .subquery()
        )
        pending = (
            await db.execute(
                select(SocialComplianceOperation)
                .join(
                    latest_attempts,
                    (SocialComplianceOperation.request_id == latest_attempts.c.request_id)
                    & (
                        SocialComplianceOperation.attempt_number
                        == latest_attempts.c.attempt_number
                    ),
                )
                .where(
                    SocialComplianceOperation.status == "retryable",
                    SocialComplianceOperation.operation_type == "source_deletion",
                    SocialComplianceOperation.post_id.is_not(None),
                )
                .order_by(SocialComplianceOperation.created_at)
                .limit(max(1, min(limit, MAX_LIFECYCLE_BATCH)))
            )
        ).scalars().all()
        succeeded = 0
        retryable = 0
        for operation in pending:
            result = await self.takedown(
                db,
                post_id=operation.post_id,
                trigger_source=operation.trigger_source,
                request_id=operation.request_id,
                attempt_number=operation.attempt_number + 1,
            )
            if result["status"] == "succeeded":
                succeeded += 1
            else:
                retryable += 1
        return {"succeeded": succeeded, "retryable": retryable}

    async def _find_source(
        self, db: AsyncSession, platform: str, external_post_id: str
    ) -> Optional[SocialMediaPost]:
        return (
            await db.execute(
                select(SocialMediaPost)
                .where(
                    SocialMediaPost.platform == platform,
                    SocialMediaPost.external_post_id == external_post_id,
                )
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _refresh_source(
        self,
        db: AsyncSession,
        post: SocialMediaPost,
        source: ProviderPost,
        allowed_fields: frozenset[str],
    ) -> None:
        await db.execute(
            delete(SocialPostDerivedArtifact).where(
                SocialPostDerivedArtifact.social_post_id == post.id
            )
        )
        post.external_post_id = (
            source.external_post_id
            if "external_post_id" in allowed_fields
            else post.external_post_id
        )
        post.original_url = (
            source.original_url if "original_url" in allowed_fields else None
        )
        post.text_content = (
            source.text_content if "text_content" in allowed_fields else None
        )
        post.posted_at = source.posted_at if "posted_at" in allowed_fields else None
        post.matched_keywords = (
            match_flood_keywords(source.text_content)
            if "matched_keywords" in allowed_fields
            else []
        )
        if "location" in allowed_fields:
            post.location_text = source.location_text
            latitude, longitude = source.latitude, source.longitude
            if (
                latitude is None
                or longitude is None
                or not (-90 <= latitude <= 90 and -180 <= longitude <= 180)
            ):
                post.latitude = None
                post.longitude = None
                post.ward_id = None
                post.geolocation_confidence = None
                post.ward_assignment_provenance = (
                    "invalid_coordinates_ignored"
                    if source.latitude is not None or source.longitude is not None
                    else "text_location_unresolved"
                    if source.location_text
                    else "no_location_metadata"
                )
            else:
                from backend.pipeline.social_collection import resolve_unique_ward

                post.latitude = latitude
                post.longitude = longitude
                (
                    post.ward_id,
                    post.geolocation_confidence,
                    post.ward_assignment_provenance,
                ) = await resolve_unique_ward(db, latitude, longitude)
        else:
            post.location_text = None
            post.latitude = None
            post.longitude = None
            post.ward_id = None
            post.geolocation_confidence = None
            post.ward_assignment_provenance = None
        post.media_references = (
            source.media_references
            if "media_references" in allowed_fields
            else []
        )
        post.source_provenance = {"provider": post.platform, "refresh": "official_lookup"}

    async def _record_reconcile_failure(
        self,
        db: AsyncSession,
        post: SocialMediaPost,
        request_id: uuid.UUID,
        attempt_number: int,
        exc: Exception,
        now: datetime,
    ) -> None:
        post_id = post.id
        previous_platform = post.platform
        await db.rollback()
        current_post = await db.get(SocialMediaPost, post_id, with_for_update=True)
        error_code = _safe_error_code(exc)
        if current_post:
            current_post.source_status = "pending_compliance"
            current_post.reconcile_attempt_count = attempt_number
            current_post.next_reconcile_at = (
                self._retry_at(attempt_number)
                if attempt_number < MAX_RECONCILE_ATTEMPTS
                else None
            )
        _append_operation(
            db,
            request_id=request_id,
            attempt_number=attempt_number,
            operation_type="source_reconciliation",
            platform=current_post.platform if current_post else previous_platform,
            post_id=current_post.id if current_post else None,
            trigger_source="scheduled_reconciliation",
            status=(
                "retryable"
                if attempt_number < MAX_RECONCILE_ATTEMPTS
                else "failed"
            ),
            outcome="provider_check_failed",
            error_code=error_code,
        )
        await db.commit()
        logger.warning(
            "Social source reconciliation failed",
            extra={
                "platform": current_post.platform if current_post else previous_platform,
                "error_code": error_code,
                "attempt_number": attempt_number,
            },
        )

    @staticmethod
    def _retry_at(attempt_number: int) -> datetime:
        return datetime.now(timezone.utc) + timedelta(
            minutes=min(2**max(0, attempt_number - 1), 60)
        )


social_lifecycle_service = SocialLifecycleService()
