"""Provider-driven collection and persistence for public social-media signals."""

import logging
import hmac
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.models.social_media_post import (
    SocialCollectionRun,
    SocialComplianceOperation,
    SocialComplianceTombstone,
    SocialMediaPost,
)
from backend.models.ward import Ward
from backend.pipeline.social_providers import (
    MAX_PAGES,
    REQUEST_TIMEOUT_SECONDS,
    ProviderPost,
    SocialProvider,
    SocialProviderError,
    build_social_providers,
    load_keyword_config,
    match_flood_keywords,
    social_search_query,
)
from backend.pipeline.social_retention import (
    collection_policy_ready,
    provider_retention_policy,
)

logger = logging.getLogger("fip.social.collection")
TOMBSTONE_INTEGRITY_FAILURES = (
    "redacted_collection_remains_blocked",
    "expired_collection_remains_blocked",
    "source_unavailable_redacted_collection_blocked",
    "source_not_locally_present_collection_remains_blocked",
)


async def _has_unrecoverable_tombstone_gaps(
    db: AsyncSession, platform: str
) -> bool:
    result = await db.execute(
        select(func.count(SocialComplianceOperation.id)).where(
            SocialComplianceOperation.platform == platform,
            SocialComplianceOperation.outcome.in_(TOMBSTONE_INTEGRITY_FAILURES),
        )
    )
    return bool(result.scalar_one())


async def resolve_unique_ward(
    db: AsyncSession, latitude: float, longitude: float
) -> tuple[Optional[str], Optional[float], Optional[str]]:
    """Assign only a uniquely containing ward; ambiguous and unmatched points remain null."""
    matches = (
        await db.execute(
            select(Ward.ward_id)
            .where(
                func.ST_Covers(
                    Ward.geom,
                    func.ST_SetSRID(func.ST_Point(longitude, latitude), 4326),
                )
            )
            .order_by(Ward.ward_id)
        )
    ).scalars().all()
    if len(matches) == 1:
        return matches[0], 1.0, "post_coordinates_st_covers"
    if len(matches) > 1:
        return None, None, "ambiguous_boundary"
    return None, None, "outside_wards"


def _validated_point(post: ProviderPost) -> tuple[Optional[float], Optional[float]]:
    lat, lon = post.latitude, post.longitude
    if lat is None or lon is None:
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    return float(lat), float(lon)


class SocialCollectionService:
    """Bounded collection coordinator; source API failures never create fake records."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        providers: Optional[Sequence[SocialProvider]] = None,
        max_pages: int = MAX_PAGES,
    ):
        self.settings = settings or get_settings()
        self.providers = list(
            providers if providers is not None else build_social_providers(self.settings)
        )
        self.max_pages = max(1, min(max_pages, MAX_PAGES))
        self.keyword_config = load_keyword_config()

    async def collect(self, db: AsyncSession) -> dict[str, Any]:
        run_results = []
        for provider in self.providers:
            query = social_search_query(provider.name)
            started_at = datetime.now(timezone.utc)
            if not self.settings.social_collection_enabled:
                status = "disabled" if provider.is_configured() else "not_configured"
                completed_at = datetime.now(timezone.utc)
                db.add(
                    SocialCollectionRun(
                        platform=provider.name,
                        started_at=started_at,
                        completed_at=completed_at,
                        status=status,
                        collected_count=0,
                        error_code=None,
                        provenance={"provider": provider.name, "query_label": "mumbai_flood_terms"},
                    )
                )
                run_results.append(
                    {"platform": provider.name, "status": status, "inserted": 0}
                )
                logger.info(
                    "Social provider collection is disabled",
                    extra={"provider": provider.name, "configured": provider.is_configured()},
                )
                continue
            if not collection_policy_ready(self.settings, provider.name):
                completed_at = datetime.now(timezone.utc)
                db.add(
                    SocialCollectionRun(
                        platform=provider.name,
                        started_at=started_at,
                        completed_at=completed_at,
                        status="policy_blocked",
                        collected_count=0,
                        error_code="retention_policy_unavailable",
                        provenance={"provider": provider.name, "query_label": "mumbai_flood_terms"},
                    )
                )
                run_results.append(
                    {"platform": provider.name, "status": "policy_blocked", "inserted": 0}
                )
                logger.warning(
                    "Social collection blocked because provider lifecycle policy is incomplete",
                    extra={"provider": provider.name},
                )
                continue
            if await _has_unrecoverable_tombstone_gaps(db, provider.name):
                completed_at = datetime.now(timezone.utc)
                db.add(
                    SocialCollectionRun(
                        platform=provider.name,
                        started_at=started_at,
                        completed_at=completed_at,
                        status="policy_blocked",
                        collected_count=0,
                        error_code="tombstone_integrity_blocked",
                        provenance={"provider": provider.name, "query_label": "mumbai_flood_terms"},
                    )
                )
                run_results.append(
                    {"platform": provider.name, "status": "policy_blocked", "inserted": 0}
                )
                logger.error(
                    "Social collection blocked because a prior removal lacks a tombstone",
                    extra={"provider": provider.name},
                )
                continue
            if not provider.is_configured():
                completed_at = datetime.now(timezone.utc)
                db.add(
                    SocialCollectionRun(
                        platform=provider.name,
                        started_at=started_at,
                        completed_at=completed_at,
                        status="not_configured",
                        collected_count=0,
                        error_code=None,
                        provenance={"provider": provider.name, "query_label": "mumbai_flood_terms"},
                    )
                )
                run_results.append(
                    {"platform": provider.name, "status": "not_configured", "inserted": 0}
                )
                logger.info(
                    "Social provider is not configured",
                    extra={"provider": provider.name},
                )
                continue

            try:
                posts = await self._fetch_provider_posts(provider, query)
                candidates = [
                    (post, match_flood_keywords(post.text_content, self.keyword_config))
                    for post in posts
                ]
                candidates = [(post, matched) for post, matched in candidates if matched]
                inserted = await self._insert_posts(db, provider, candidates)
                status = "success"
                error_code = None
            except SocialProviderError as exc:
                inserted = 0
                status = "error"
                error_code = exc.code
                logger.warning(
                    "Social provider collection failed",
                    extra={"provider": provider.name, "error_code": error_code},
                )

            completed_at = datetime.now(timezone.utc)
            db.add(
                SocialCollectionRun(
                    platform=provider.name,
                    started_at=started_at,
                    completed_at=completed_at,
                    status=status,
                    collected_count=inserted,
                    error_code=error_code,
                    provenance={"provider": provider.name, "query_label": "mumbai_flood_terms"},
                )
            )
            run_results.append(
                {"platform": provider.name, "status": status, "inserted": inserted}
            )
            logger.info(
                "Social provider collection completed",
                extra={
                    "provider": provider.name,
                    "status": status,
                    "inserted_count": inserted,
                },
            )
        await db.commit()
        return {
            "providers": run_results,
            "inserted_count": sum(result["inserted"] for result in run_results),
        }

    async def _fetch_provider_posts(
        self, provider: SocialProvider, query: str
    ) -> list[ProviderPost]:
        collected: list[ProviderPost] = []
        cursor: Optional[str] = None
        timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for _ in range(self.max_pages):
                page, cursor = await provider.fetch_page(client, query, cursor)
                collected.extend(page)
                if not cursor:
                    break
        return collected

    async def _insert_posts(
        self,
        db: AsyncSession,
        provider: SocialProvider,
        candidates: list[tuple[ProviderPost, list[str]]],
    ) -> int:
        rows = []
        collection_id = str(uuid.uuid4())
        policy = provider_retention_policy(self.settings, provider.name)
        tombstone_key = self.settings.social_tombstone_hmac_key.encode("utf-8")
        candidate_digests = {
            hmac.digest(
                tombstone_key,
                f"{provider.name}\0{post.external_post_id}".encode("utf-8"),
                "sha256",
            ).hex(): post.external_post_id
            for post, _ in candidates
            if tombstone_key
        }
        blocked_ids: set[str] = set()
        if candidate_digests:
            existing_tombstones = await db.execute(
                select(SocialComplianceTombstone.source_id_digest).where(
                    SocialComplianceTombstone.platform == provider.name,
                    SocialComplianceTombstone.source_id_digest.in_(
                        candidate_digests.keys()
                    ),
                )
            )
            blocked_digests = set(existing_tombstones.scalars().all())
            blocked_ids = {
                candidate_digests[digest] for digest in blocked_digests
            }
        for post, matched_keywords in candidates:
            if post.external_post_id in blocked_ids:
                continue
            latitude, longitude = _validated_point(post)
            if "location" not in policy.allowed_fields:
                latitude, longitude = None, None
            ward_id = None
            confidence = None
            if post.latitude is not None or post.longitude is not None:
                assignment_provenance = (
                    "invalid_coordinates_ignored"
                    if latitude is None or longitude is None
                    else None
                )
            elif "location" in policy.allowed_fields and post.location_text:
                assignment_provenance = "text_location_unresolved"
            else:
                assignment_provenance = "no_location_metadata"
            if latitude is not None and longitude is not None:
                ward_id, confidence, assignment_provenance = await resolve_unique_ward(
                    db, latitude, longitude
                )
            collected_at = datetime.now(timezone.utc)
            rows.append(
                {
                    "platform": provider.name,
                    "external_post_id": post.external_post_id,
                    "original_url": (
                        post.original_url
                        if "original_url" in policy.allowed_fields
                        else None
                    ),
                    "text_content": (
                        post.text_content
                        if "text_content" in policy.allowed_fields
                        else None
                    ),
                    "posted_at": (
                        post.posted_at if "posted_at" in policy.allowed_fields else None
                    ),
                    "collected_at": collected_at,
                    "location_text": (
                        post.location_text if "location" in policy.allowed_fields else None
                    ),
                    "latitude": latitude,
                    "longitude": longitude,
                    "ward_id": ward_id,
                    "geolocation_confidence": confidence,
                    "ward_assignment_provenance": assignment_provenance,
                    "matched_keywords": (
                        matched_keywords
                        if "matched_keywords" in policy.allowed_fields
                        else []
                    ),
                    "media_references": (
                        post.media_references
                        if "media_references" in policy.allowed_fields
                        else []
                    ),
                    "processing_status": "collected",
                    "source_status": "unverified",
                    "expires_at": policy.expiration_at(collected_at),
                    "last_verified_at": None,
                    "next_reconcile_at": collected_at,
                    "reconcile_attempt_count": 0,
                    "source_provenance": {
                        "provider": provider.name,
                        "api_endpoint": getattr(provider, "search_url", ""),
                        "collection_id": collection_id,
                        "query_label": "mumbai_flood_terms",
                    },
                }
            )
        if not rows:
            return 0
        statement = (
            pg_insert(SocialMediaPost)
            .values(rows)
            .on_conflict_do_nothing(
                constraint="uq_social_media_posts_platform_external"
            )
            .returning(SocialMediaPost.id)
        )
        inserted = (await db.execute(statement)).scalars().all()

        # Run Engine C NLP classification on inserted posts and persist derived artifacts
        if inserted and isinstance(db, AsyncSession):
            try:
                from backend.pipeline.social_nlp import social_nlp_service
                new_posts = (
                    await db.execute(
                        select(SocialMediaPost).where(SocialMediaPost.id.in_(inserted))
                    )
                ).scalars().all()
                for post in new_posts:
                    try:
                        await social_nlp_service.process_post(db, post)
                    except Exception as exc:
                        logger.warning(
                            "NLP processing skipped for post %s on platform %s: %s",
                            getattr(post, "id", None),
                            getattr(post, "platform", None),
                            exc,
                        )
            except Exception as outer_exc:
                logger.warning("Post-insert NLP batch processing note: %s", outer_exc)

        return len(inserted)


social_collection_service = SocialCollectionService()
