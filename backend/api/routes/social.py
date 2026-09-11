"""
FastAPI route endpoints for Social Media Intelligence & NLP Triage (Engine C).
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_db
from backend.models.social import SocialSignal
from backend.schemas.social import (
    SocialSignalCreate,
    SocialSignalResponse,
    SocialSignalListResponse,
    SocialSummaryResponse,
    HotspotKeyword,
)
from backend.pipeline.social_ingest import social_ingest_pipeline

router = APIRouter(prefix="/social", tags=["Social Media Intelligence"])


@router.get(
    "/signals",
    response_model=SocialSignalListResponse,
    summary="List ingested social intelligence signals with urgency & ward filters"
)
async def list_social_signals(
    ward_id: Optional[str] = Query(None, description="Filter by administrative ward ID"),
    classification: Optional[str] = Query(None, description="Filter by classification (evacuation_needed, urgent, waterlogging, noise)"),
    urgency_min: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum urgency score threshold"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
) -> SocialSignalListResponse:
    """
    Retrieve real-time and historical social media signals parsed by Engine C.
    """
    conditions = []
    if ward_id:
        conditions.append(SocialSignal.ward_id == ward_id)
    if classification:
        conditions.append(SocialSignal.classification == classification)
    if urgency_min is not None:
        conditions.append(SocialSignal.urgency_score >= urgency_min)

    stmt = (
        select(SocialSignal)
        .where(and_(*conditions) if conditions else True)
        .order_by(desc(SocialSignal.posted_at))
        .offset(offset)
        .limit(limit)
    )

    res = await db.execute(stmt)
    signals = res.scalars().all()

    # Total count query
    count_stmt = select(func.count(SocialSignal.id)).where(and_(*conditions) if conditions else True)
    count_res = await db.execute(count_stmt)
    total = count_res.scalar() or 0

    return SocialSignalListResponse(
        total=total,
        signals=[SocialSignalResponse.model_validate(s) for s in signals]
    )


@router.post(
    "/signals",
    response_model=SocialSignalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a new social post, run Engine C NLP, and cache urgency score"
)
async def ingest_social_post(
    payload: SocialSignalCreate,
    db: AsyncSession = Depends(get_db)
) -> SocialSignalResponse:
    """
    Ingest a citizen tweet, telegram message, or 1916 helpline transcript.
    Processes the payload through IndicBERT / DistilBERT rules, geocodes landmarks,
    and updates ward situational awareness caches.
    """
    signal = await social_ingest_pipeline.process_and_store_signal(
        db=db,
        source=payload.source,
        content_text=payload.content_text,
        author_handle=payload.author_handle,
        language=payload.language,
        ward_id=payload.ward_id,
        location_name=payload.location_name,
        posted_at=payload.posted_at
    )
    return SocialSignalResponse.model_validate(signal)


@router.post(
    "/simulate",
    response_model=List[SocialSignalResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Seed realistic multilingual Mumbai flood social signals for testing"
)
async def simulate_social_feed(
    db: AsyncSession = Depends(get_db)
) -> List[SocialSignalResponse]:
    """
    Triggers simulated incoming batch of Mumbai monsoon tweets, telegram warnings,
    and helpline reports across Kurla, Dadar, Dharavi, Sion, and Andheri.
    """
    created = await social_ingest_pipeline.ingest_simulation_batch(db)
    return [SocialSignalResponse.model_validate(s) for s in created]


@router.get(
    "/summary",
    response_model=SocialSummaryResponse,
    summary="Aggregated situational awareness stats, hotspots, and sentiment distribution"
)
async def get_social_summary(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db)
) -> SocialSummaryResponse:
    """
    Returns high-level situational metrics over the specified window (default: 24h):
    - Total signals
    - Urgent and evacuation counts
    - Top hotspots by mention count and average urgency
    - Classification breakdown
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Classification counts
    cls_stmt = (
        select(SocialSignal.classification, func.count(SocialSignal.id))
        .where(SocialSignal.posted_at >= cutoff)
        .group_by(SocialSignal.classification)
    )
    cls_res = await db.execute(cls_stmt)
    class_dist = {row[0]: row[1] for row in cls_res.all()}

    total_signals = sum(class_dist.values())
    urgent_count = class_dist.get("urgent", 0)
    evac_count = class_dist.get("evacuation_needed", 0)

    # Top hotspots from location_name
    hotspot_stmt = (
        select(
            SocialSignal.location_name,
            SocialSignal.ward_id,
            func.count(SocialSignal.id).label("cnt"),
            func.avg(SocialSignal.urgency_score).label("avg_urgency")
        )
        .where(
            and_(
                SocialSignal.posted_at >= cutoff,
                SocialSignal.location_name.isnot(None)
            )
        )
        .group_by(SocialSignal.location_name, SocialSignal.ward_id)
        .order_by(desc("cnt"))
        .limit(8)
    )
    hotspot_res = await db.execute(hotspot_stmt)
    hotspots = [
        HotspotKeyword(
            landmark=row[0],
            ward_id=row[1],
            count=row[2],
            avg_urgency=round(float(row[3]), 2)
        )
        for row in hotspot_res.all()
    ]

    return SocialSummaryResponse(
        total_signals_24h=total_signals,
        urgent_signals_count=urgent_count,
        evacuation_mentions_count=evac_count,
        top_hotspots=hotspots,
        classification_distribution=class_dist
    )
