"""Authenticated read APIs for collected public social-media signals."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.operator_auth import require_verification_operator
from backend.config import Settings, get_settings
from backend.models.database import get_db
from backend.models.social_media_post import (
    SocialCollectionRun,
    SocialComplianceOperation,
    SocialMediaPost,
)
from backend.pipeline.social_providers import build_social_providers
from backend.schemas.social_media import (
    SocialComplianceOperationResponse,
    SocialMediaPostPage,
    SocialMediaPostResponse,
    SocialProviderComplianceEvent,
    SocialProviderStatus,
    SocialStatusResponse,
    SocialSummaryResponse,
    SocialTakedownRequest,
)
from backend.pipeline.social_lifecycle import social_lifecycle_service
from backend.pipeline.social_nlp import social_nlp_service
from backend.pipeline.social_retention import provider_retention_policy

router = APIRouter(
    prefix="/social",
    tags=["Social Media Intelligence"],
    dependencies=[Depends(require_verification_operator)],
)


@router.get("/status", response_model=SocialStatusResponse)
async def get_social_status(
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SocialStatusResponse:
    """Report configured sources and persisted last successful collection times."""
    response.headers["Cache-Control"] = "no-store"
    provider_statuses = []
    latest_success_values = []
    for provider in build_social_providers(settings):
        configured = provider.is_configured()
        last_success = await db.execute(
            select(func.max(SocialCollectionRun.completed_at)).where(
                SocialCollectionRun.platform == provider.name,
                SocialCollectionRun.status == "success",
            )
        )
        last_success_at = last_success.scalar_one_or_none()
        latest_run = await db.execute(
            select(SocialCollectionRun.status)
            .where(SocialCollectionRun.platform == provider.name)
            .order_by(SocialCollectionRun.completed_at.desc())
            .limit(1)
        )
        latest_status = latest_run.scalar_one_or_none()
        if last_success_at is not None:
            latest_success_values.append(last_success_at)
        state = (
            "not_configured"
            if not configured
            else "disabled"
            if not settings.social_collection_enabled
            else "error"
            if latest_status == "error"
            else "configured"
        )
        provider_statuses.append(
            SocialProviderStatus(
                platform=provider.name,
                state=state,
                configured=configured,
                last_success_at=last_success_at,
                lifecycle_policy_ready=provider_retention_policy(
                    settings, provider.name
                ).can_collect,
            )
        )
    return SocialStatusResponse(
        providers=provider_statuses,
        latest_success_at=max(latest_success_values) if latest_success_values else None,
    )


@router.get("/posts", response_model=SocialMediaPostPage)
async def list_social_posts(
    response: Response,
    platform: Optional[str] = Query(None, pattern="^(reddit|x)$"),
    posted_from: Optional[datetime] = None,
    posted_to: Optional[datetime] = None,
    keyword: Optional[str] = Query(None, min_length=1, max_length=80),
    processing_status: Optional[str] = Query(None, min_length=1, max_length=32),
    source_status: Optional[str] = Query(
        None,
        pattern="^(unverified|current|pending_compliance|unavailable|expired|deleted)$",
    ),
    ward_id: Optional[str] = Query(None, min_length=1, max_length=20),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> SocialMediaPostPage:
    """List collected records with bounded pagination and source/time/location filters."""
    response.headers["Cache-Control"] = "no-store"
    if (posted_from and posted_from.tzinfo is None) or (
        posted_to and posted_to.tzinfo is None
    ):
        raise HTTPException(
            status_code=422,
            detail="Social post date filters must include a timezone.",
        )
    if posted_from and posted_to and posted_from > posted_to:
        raise HTTPException(status_code=422, detail="posted_from must not be after posted_to.")

    conditions = []
    if platform:
        conditions.append(SocialMediaPost.platform == platform)
    if posted_from:
        conditions.append(SocialMediaPost.posted_at >= posted_from)
    if posted_to:
        conditions.append(SocialMediaPost.posted_at <= posted_to)
    if keyword:
        conditions.append(SocialMediaPost.matched_keywords.contains([keyword]))
    if processing_status:
        conditions.append(SocialMediaPost.processing_status == processing_status)
    if source_status:
        conditions.append(SocialMediaPost.source_status == source_status)
    if ward_id:
        conditions.append(SocialMediaPost.ward_id == ward_id)

    posts_result = await db.execute(
        select(SocialMediaPost)
        .where(*conditions)
        .order_by(
            SocialMediaPost.posted_at.desc().nullslast(),
            SocialMediaPost.collected_at.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    count_result = await db.execute(
        select(func.count(SocialMediaPost.id)).where(*conditions)
    )
    posts = posts_result.scalars().all()
    post_ids = [p.id for p in posts]
    nlp_map: dict[int, dict[str, Any]] = {}
    if post_ids:
        from backend.models.social_media_post import SocialPostDerivedArtifact
        artifacts_res = await db.execute(
            select(SocialPostDerivedArtifact).where(
                SocialPostDerivedArtifact.social_post_id.in_(post_ids),
                SocialPostDerivedArtifact.artifact_type == "nlp",
            )
        )
        for art in artifacts_res.scalars().all():
            nlp_map[art.social_post_id] = art.payload

    return SocialMediaPostPage(
        total=count_result.scalar_one(),
        limit=limit,
        offset=offset,
        posts=[_post_response(post, nlp_map.get(post.id)) for post in posts],
    )


@router.get("/posts/{post_id}", response_model=SocialMediaPostResponse)
async def get_social_post(
    post_id: int,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> SocialMediaPostResponse:
    response.headers["Cache-Control"] = "no-store"
    post = await db.get(SocialMediaPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Social post not found.")
    from backend.models.social_media_post import SocialPostDerivedArtifact
    art_res = await db.execute(
        select(SocialPostDerivedArtifact.payload).where(
            SocialPostDerivedArtifact.social_post_id == post_id,
            SocialPostDerivedArtifact.artifact_type == "nlp",
        )
    )
    nlp_payload = art_res.scalar_one_or_none()
    return _post_response(post, nlp_payload)


@router.post("/posts/{post_id}/reprocess-nlp", response_model=SocialMediaPostResponse)
async def reprocess_social_post_nlp(
    post_id: int,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> SocialMediaPostResponse:
    """Reprocess a social post through Engine C NLP and update its derived artifact."""
    response.headers["Cache-Control"] = "no-store"
    post = await db.get(SocialMediaPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Social post not found.")
    nlp_payload = await social_nlp_service.process_post(db, post, reprocess=True)
    await db.commit()
    await db.refresh(post)
    return _post_response(post, nlp_payload)


@router.get("/summary", response_model=SocialSummaryResponse)
async def get_social_summary(
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> SocialSummaryResponse:
    response.headers["Cache-Control"] = "no-store"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    now = datetime.now(timezone.utc)
    eligible = (
        SocialMediaPost.source_status == "current",
        SocialMediaPost.expires_at.is_not(None),
        SocialMediaPost.expires_at > now,
        SocialMediaPost.last_verified_at.is_not(None),
        SocialMediaPost.next_reconcile_at.is_not(None),
        SocialMediaPost.next_reconcile_at > now,
    )
    total_result = await db.execute(
        select(func.count(SocialMediaPost.id)).where(*eligible)
    )
    recent_result = await db.execute(
        select(func.count(SocialMediaPost.id)).where(
            SocialMediaPost.collected_at >= cutoff, *eligible
        )
    )
    platform_result = await db.execute(
        select(SocialMediaPost.platform, func.count(SocialMediaPost.id)).group_by(
            SocialMediaPost.platform
        ).where(*eligible)
    )
    latest_result = await db.execute(
        select(func.max(SocialMediaPost.collected_at)).where(*eligible)
    )
    return SocialSummaryResponse(
        total_posts=total_result.scalar_one(),
        posts_last_24h=recent_result.scalar_one(),
        platform_breakdown={row[0]: row[1] for row in platform_result.all()},
        latest_collected_at=latest_result.scalar_one_or_none(),
    )


def _post_response(
    post: SocialMediaPost, nlp_payload: Optional[dict[str, Any]] = None
) -> SocialMediaPostResponse:
    response = SocialMediaPostResponse.model_validate(post)
    if nlp_payload is not None:
        response = response.model_copy(update={"nlp_analysis": nlp_payload})
    now = datetime.now(timezone.utc)
    is_expired = bool(
        response.expires_at
        and response.expires_at <= now
    )
    if is_expired:
        response = response.model_copy(update={"source_status": "expired"})
    is_current = (
        response.source_status == "current"
        and response.expires_at is not None
        and response.expires_at > now
        and response.last_verified_at is not None
        and response.next_reconcile_at is not None
        and response.next_reconcile_at > now
    )
    if not is_current:
        if response.source_status == "current":
            response = response.model_copy(update={"source_status": "unverified"})
        response = response.model_copy(
            update={
                "external_post_id": None,
                "original_url": None,
                "text_content": None,
                "posted_at": None,
                "location_text": None,
                "latitude": None,
                "longitude": None,
                "ward_id": None,
                "geolocation_confidence": None,
                "ward_assignment_provenance": None,
                "matched_keywords": [],
                "media_references": [],
                "source_provenance": {},
            }
        )
    return response


@router.post("/compliance/takedowns")
async def submit_social_takedown(
    request: SocialTakedownRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        result = await social_lifecycle_service.takedown(
            db, post_id=request.post_id, trigger_source="operator_takedown"
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Social post not found.") from exc
    status_code = 200 if result["status"] == "succeeded" else 202
    return JSONResponse(result, status_code=status_code, headers={"Cache-Control": "no-store"})


@router.post("/compliance/provider-events")
async def submit_social_provider_event(
    request: SocialProviderComplianceEvent,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        result = await social_lifecycle_service.handle_provider_event(
            db,
            platform=request.platform,
            external_post_id=request.external_post_id,
            action=request.action,
            event_id=request.event_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Social post not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported provider event.") from exc
    status_code = 200 if result["status"] in {"succeeded", "not_found"} else 202
    return JSONResponse(result, status_code=status_code, headers={"Cache-Control": "no-store"})


@router.get(
    "/compliance/operations",
    response_model=list[SocialComplianceOperationResponse],
)
async def list_social_compliance_operations(
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[SocialComplianceOperation]:
    response.headers["Cache-Control"] = "no-store"
    result = await db.execute(
        select(SocialComplianceOperation)
        .order_by(SocialComplianceOperation.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
