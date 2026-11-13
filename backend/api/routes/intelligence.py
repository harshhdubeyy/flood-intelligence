"""
Citizen Report Intelligence API endpoints.

Provides ward-level analytics, reliability scoring, hotspot detection,
and citizen flood intelligence scores derived from citizen-submitted reports.
"""

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_db
from backend.models.report import CitizenReport
from backend.models.ward import Ward
from backend.services.report_intelligence import ReportIntelligenceEngine
from backend.schemas.intelligence import (
    WardIncidentAnalytics,
    WardIntelligenceScore,
    ReportReliability,
    FloodHotspot,
    WardIntelligenceResponse,
    IntelligenceSummary,
)

logger = logging.getLogger("fip.api.intelligence")

router = APIRouter(prefix="/reports/intelligence", tags=["Citizen Report Intelligence"])


@router.get(
    "/wards",
    response_model=List[WardIntelligenceResponse],
    status_code=status.HTTP_200_OK,
    summary="Ward-wise report analytics and intelligence scores",
)
async def get_wards_intelligence(
    db: AsyncSession = Depends(get_db),
) -> List[WardIntelligenceResponse]:
    """Get citizen flood intelligence for all wards that have reports."""
    engine = ReportIntelligenceEngine(db)
    analytics_list = await engine.get_all_wards_analytics()
    results = []

    for analytics in analytics_list:
        ward_id = analytics["ward_id"]
        intel = await engine.calculate_ward_intelligence_score(ward_id)

        non_dup_stmt = select(CitizenReport).where(
            CitizenReport.ward_id == ward_id,
            CitizenReport.is_duplicate.is_(False),
        )
        non_dup_res = await db.execute(non_dup_stmt)
        non_dup_reports = non_dup_res.scalars().all()

        reliability_scores = [engine.calculate_report_reliability(r) for r in non_dup_reports]
        avg_reliability = (
            sum(r["reliability_score"] for r in reliability_scores) / len(reliability_scores)
            if reliability_scores else 0.0
        )
        reliability_summary = {
            "avg_reliability": round(avg_reliability, 4),
            "total_scored": len(reliability_scores),
            "high_reliability": sum(1 for r in reliability_scores if r["reliability_score"] >= 0.7),
            "low_reliability": sum(1 for r in reliability_scores if r["reliability_score"] < 0.4),
        }

        results.append(WardIntelligenceResponse(
            analytics=WardIncidentAnalytics(**analytics),
            intelligence=WardIntelligenceScore(**intel) if intel else None,
            reliability_summary=reliability_summary,
        ))

    return results


@router.get(
    "/wards/{ward_id}",
    response_model=WardIntelligenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Detailed intelligence for an individual ward",
)
async def get_ward_intelligence(
    ward_id: str,
    db: AsyncSession = Depends(get_db),
) -> WardIntelligenceResponse:
    """Get detailed citizen flood intelligence for a specific ward."""
    engine = ReportIntelligenceEngine(db)

    ward_stmt = select(Ward).where(Ward.ward_id == ward_id)
    ward_res = await db.execute(ward_stmt)
    ward = ward_res.scalar_one_or_none()
    if not ward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ward '{ward_id}' not found",
        )

    # Get analytics (works even with no reports)
    analytics = await engine.get_ward_analytics(ward_id)
    if analytics is None:
        analytics = {
            "ward_id": ward_id,
            "ward_name": ward.ward_name,
            "total_reports": 0,
            "reports_last_1h": 0,
            "reports_last_3h": 0,
            "reports_last_24h": 0,
            "cv_verified_count": 0,
            "unverified_count": 0,
            "duplicate_count": 0,
            "severe_count": 0,
            "avg_severity": 0.0,
            "latest_incident": None,
        }

    # Calculate intelligence score (may return None if no non-duplicate reports)
    intel = await engine.calculate_ward_intelligence_score(ward_id)

    # Get non-duplicate reports for reliability scoring
    non_dup_stmt = select(CitizenReport).where(
        CitizenReport.ward_id == ward_id,
        CitizenReport.is_duplicate.is_(False),
    )
    non_dup_res = await db.execute(non_dup_stmt)
    non_dup_reports = non_dup_res.scalars().all()

    reliability_scores = [engine.calculate_report_reliability(r) for r in non_dup_reports]
    avg_reliability = (
        sum(r["reliability_score"] for r in reliability_scores) / len(reliability_scores)
        if reliability_scores else 0.0
    )
    reliability_summary = {
        "avg_reliability": round(avg_reliability, 4),
        "total_scored": len(reliability_scores),
        "high_reliability": sum(1 for r in reliability_scores if r["reliability_score"] >= 0.7),
        "low_reliability": sum(1 for r in reliability_scores if r["reliability_score"] < 0.4),
    }

    if intel:
        intel["avg_reliability"] = round(avg_reliability, 4)

    return WardIntelligenceResponse(
        analytics=WardIncidentAnalytics(**analytics),
        intelligence=WardIntelligenceScore(**intel) if intel else None,
        reliability_summary=reliability_summary,
    )


@router.get(
    "/reliability/{report_id}",
    response_model=ReportReliability,
    status_code=status.HTTP_200_OK,
    summary="Reliability score for an individual citizen report",
)
async def get_report_reliability(
    report_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReportReliability:
    """Get the reliability score for a specific citizen report."""
    engine = ReportIntelligenceEngine(db)

    stmt = select(CitizenReport).where(CitizenReport.report_id == report_id)
    res = await db.execute(stmt)
    report = res.scalar_one_or_none()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found",
        )

    result = engine.calculate_report_reliability(report)
    return ReportReliability(**result)


@router.get(
    "/hotspots",
    response_model=List[FloodHotspot],
    status_code=status.HTTP_200_OK,
    summary="Geographic flood incident clusters",
)
async def get_flood_hotspots(
    cluster_distance_m: float = Query(100.0, description="Clustering distance in meters"),
    min_reports: int = Query(2, description="Minimum reports to form a hotspot"),
    recency_hours: int = Query(24, description="Recency window in hours"),
    db: AsyncSession = Depends(get_db),
) -> List[FloodHotspot]:
    """Detect geographic clusters of citizen flood reports."""
    engine = ReportIntelligenceEngine(db)
    hotspots = await engine.detect_hotspots(
        cluster_distance_m=cluster_distance_m,
        min_reports=min_reports,
        recency_hours=recency_hours,
    )
    return [FloodHotspot(**h) for h in hotspots]


@router.get(
    "/summary",
    response_model=IntelligenceSummary,
    status_code=status.HTTP_200_OK,
    summary="Overall citizen flood intelligence summary",
)
async def get_intelligence_summary(
    db: AsyncSession = Depends(get_db),
) -> IntelligenceSummary:
    """Get overall citizen flood intelligence summary across all wards."""
    engine = ReportIntelligenceEngine(db)
    summary = await engine.get_intelligence_summary()
    return IntelligenceSummary(**summary)