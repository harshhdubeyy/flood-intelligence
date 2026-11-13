"""
API endpoints for crowdsourced citizen flood report intake, duplicate deduplication,
and Computer Vision image verification.
"""

import logging
import os
import re
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.operator_auth import require_verification_operator
from backend.models.database import get_db
from backend.models.report import CitizenReport, CitizenReportNLPAnalysis
from backend.models.flood_event import FloodEvent, FloodEventVerificationHistory
from backend.models.ward import Ward
from backend.services.evidence_storage import build_evidence_storage
from backend.schemas.report import (
    CitizenReportResponse,
    CitizenReportListResponse,
    ReportVerificationSummary,
    ReportDetailResponse,
    ReportVerificationRequest,
    ReportVerificationResponse,
    OperatorReportQueueResponse,
    FloodEventResponse,
    FloodEventListResponse,
    FloodEventVerificationHistoryResponse,
    OperatorIdentityResponse,
)
from backend.ml.engine_b.cv_water_depth import cv_verifier
from backend.ml.engine_b.nlp_pipeline import citizen_nlp

logger = logging.getLogger("fip.api.reports")

router = APIRouter(prefix="/reports", tags=["Citizen Reports"])

# Local uploads directory for development
UPLOAD_DIR = "/tmp/flood_reports"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Allowed image MIME types and extensions
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB



def _generate_safe_filename(report_id: str, original_filename: Optional[str]) -> str:
    """Generate a safe, unique filename preventing path traversal."""
    ext = os.path.splitext(original_filename or "report.jpg")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".jpg"
    safe_id = re.sub(r"[^a-zA-Z0-9._-]", "_", report_id)
    return f"{safe_id}{ext}"


def _validate_image(upload: UploadFile) -> None:
    """Validate uploaded image file type and size."""
    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type '{content_type}'. Allowed: JPEG, JPG, PNG, WebP.",
        )
    filename = upload.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file extension '{ext}'. Allowed: .jpg, .jpeg, .png, .webp.",
        )


def _validate_image_payload(filename: str, content: bytes) -> None:
    extension = os.path.splitext(filename)[1].lower()
    valid_signatures = {
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
    }
    if not valid_signatures.get(extension, False):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Image contents do not match an allowed image format.",
        )


async def _report_coordinates(db: AsyncSession, report_id: str) -> Tuple[float, float]:
    result = await db.execute(
        select(
            func.ST_Y(CitizenReport.location).label("latitude"),
            func.ST_X(CitizenReport.location).label("longitude"),
        ).where(CitizenReport.report_id == report_id)
    )
    row = result.one()
    return float(row.latitude), float(row.longitude)


async def _resolve_unique_ward(
    db: AsyncSession, latitude: float, longitude: float
) -> Tuple[Optional[str], str]:
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
        return matches[0], "matched"
    if matches:
        return None, "ambiguous_boundary"
    return None, "outside_wards"


async def _evidence_urls_for_report(db: AsyncSession, report: CitizenReport) -> List[str]:
    urls = [report.image_url] if report.image_url else []
    records = (
        await db.execute(
            select(FloodEventVerificationHistory.evidence_image_urls)
            .where(FloodEventVerificationHistory.report_id == report.report_id)
            .order_by(FloodEventVerificationHistory.id)
        )
    ).scalars().all()
    for record_urls in records:
        for url in record_urls or []:
            if url not in urls:
                urls.append(url)
    return urls


@router.post(
    "",
    response_model=CitizenReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a citizen flood report with optional photo and automatic CV analysis"
)
async def submit_citizen_report(
    latitude: float = Form(..., description="Latitude between -90 and 90"),
    longitude: float = Form(..., description="Longitude between -180 and 180"),
    water_depth: str = Form(..., description="Categorical water depth: ankle, knee, waist, submerged"),
    description: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db)
) -> CitizenReportResponse:
    """
    Submits a flood report:
    1. Determines ward membership via PostGIS ST_Contains
    2. Runs deduplication check (reports within 50m and last 15 minutes)
    3. Analyzes image using Engine B (Computer Vision flood verifier)
    4. Persists verified report to PostGIS database
    """
    # Validate water_depth category
    water_depth_norm = water_depth.lower().strip()
    if water_depth_norm not in ("ankle", "knee", "waist", "submerged"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="water_depth must be one of: ankle, knee, waist, submerged",
        )

    # Validate coordinate ranges
    if not (-90.0 <= latitude <= 90.0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="latitude must be between -90 and 90",
        )
    if not (-180.0 <= longitude <= 180.0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="longitude must be between -180 and 180",
        )

    report_id = str(uuid.uuid4())

    try:
        # 1. Reverse-geocode ward via PostGIS
        ward_stmt = select(Ward.ward_id).where(
            func.ST_Contains(Ward.geom, func.ST_SetSRID(func.ST_Point(longitude, latitude), 4326))
        ).limit(1)
        ward_res = await db.execute(ward_stmt)
        resolved_ward_id = ward_res.scalar_one_or_none()

        # 2. Deduplication check: reports within 50 meters and last 15 minutes
        fifteen_min_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
        dup_stmt = select(CitizenReport.report_id).where(
            func.ST_DWithin(
                func.ST_Transform(CitizenReport.location, 3857),
                func.ST_Transform(func.ST_SetSRID(func.ST_Point(longitude, latitude), 4326), 3857),
                50.0,  # 50 meters
            ),
            CitizenReport.submitted_at >= fifteen_min_ago,
        ).limit(1)
        dup_res = await db.execute(dup_stmt)
        duplicate_of = dup_res.scalar_one_or_none()
        is_dup = duplicate_of is not None

        # 3. Handle photo upload and CV verification
        image_url = None
        cv_verified = False
        cv_depth_m = None
        cv_conf = None

        if image is not None:
            _validate_image(image)
            content = await image.read()
            if len(content) > MAX_IMAGE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Image too large. Maximum size is {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB.",
                )
            if len(content) < 50:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded image file is empty or too small.",
                )

            # Generate safe filename and store locally
            safe_filename = _generate_safe_filename(report_id, image.filename or "report.jpg")
            file_path = os.path.join(UPLOAD_DIR, safe_filename)
            # Path traversal guard
            real_upload_dir = os.path.realpath(UPLOAD_DIR)
            real_file_path = os.path.realpath(file_path)
            if not (
                real_file_path == real_upload_dir
                or real_file_path.startswith(real_upload_dir + os.sep)
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unsafe file path detected.",
                )
            with open(file_path, "wb") as f:
                f.write(content)
            image_url = f"/uploads/{safe_filename}"

            # Run CV verification using existing Engine B (non-blocking inference)
            try:
                analysis = cv_verifier.analyze_image_bytes(content, reported_depth=water_depth_norm)
                cv_verified = bool(analysis.get("cv_verified", False))
                cv_depth_m = analysis.get("cv_water_depth_m")
                cv_conf = analysis.get("cv_confidence")
            except Exception as cv_exc:
                logger.error(f"CV verification failed for report {report_id}: {cv_exc}")
                cv_verified = False
        else:
            # No image: NOT CV-verified. Keep citizen-reported depth separate from CV estimates.
            cv_verified = False

        # 4. Run Multilingual NLP Analysis on citizen description (Engine B)
        # Note: Citizen-reported depth is NEVER overwritten. Original description is preserved verbatim.
        nlp_result = None
        nlp_row = None
        try:
            depth_category_m = {
                "ankle": 0.15,
                "knee": 0.50,
                "waist": 1.00,
                "submerged": 1.80,
            }.get(water_depth_norm, 0.3)
            nlp_result = citizen_nlp.analyze_report_text(
                description,
                reported_category="waterlogging",
                reported_depth_m=depth_category_m,
            )
            nlp_row = CitizenReportNLPAnalysis(
                report_id=report_id,
                model_version=nlp_result["model_version"],
                classification=nlp_result["classification"],
                confidence=nlp_result["confidence"],
                urgency_score=nlp_result["urgency_score"],
                is_flood_related=nlp_result["is_flood_related"],
                is_waterlogging=nlp_result["is_waterlogging"],
                is_spam=nlp_result["is_spam"],
                detected_language=nlp_result["detected_language"],
                extracted_depth_m=nlp_result["extracted_depth_m"],
                extracted_landmarks=nlp_result["extracted_landmarks"],
                matched_keywords=nlp_result["matched_keywords"],
                provenance=nlp_result["provenance"],
                processed_at=datetime.now(timezone.utc),
            )
        except Exception as nlp_exc:
            logger.error(f"NLP analysis failed for report {report_id}: {nlp_exc}")

        # 5. Save to database
        report = CitizenReport(
            report_id=report_id,
            ward_id=resolved_ward_id,
            location=func.ST_SetSRID(func.ST_Point(longitude, latitude), 4326),
            water_depth=water_depth_norm,
            image_url=image_url,
            cv_verified=cv_verified,
            cv_water_depth_m=cv_depth_m,
            cv_confidence=cv_conf,
            description=description,
            is_duplicate=is_dup,
            duplicate_of_id=duplicate_of,
            submitted_at=datetime.now(timezone.utc),
        )
        db.add(report)
        if nlp_row is not None:
            db.add(nlp_row)
        await db.commit()
        await db.refresh(report)

        return CitizenReportResponse(
            report_id=report.report_id,
            ward_id=report.ward_id,
            latitude=latitude,
            longitude=longitude,
            water_depth=report.water_depth,
            image_url=report.image_url,
            cv_verified=report.cv_verified,
            cv_water_depth_m=report.cv_water_depth_m,
            cv_confidence=report.cv_confidence,
            description=report.description,
            is_duplicate=report.is_duplicate,
            duplicate_of_id=report.duplicate_of_id,
            operator_verification_status=report.operator_verification_status,
            submitted_at=report.submitted_at,
            nlp_analysis=nlp_result,
        )

    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error(f"Failed to submit citizen report: {exc}")
        # Clean up uploaded file if DB save failed
        if image_url:
            try:
                _path = os.path.join(UPLOAD_DIR, os.path.basename(image_url))
                if os.path.exists(_path):
                    os.remove(_path)
            except OSError:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save report due to a server error.",
        )


@router.get(
    "",
    response_model=CitizenReportListResponse,
    status_code=status.HTTP_200_OK,
    summary="List citizen reports with optional filters and pagination"
)
async def list_citizen_reports(
    ward_id: Optional[str] = None,
    verified_only: bool = False,
    water_depth: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
) -> CitizenReportListResponse:
    """
    Retrieve incident reports ordered chronologically by submission time.
    Supports filtering by ward, CV verification status, and water depth.
    """
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 100",
        )
    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="offset must be >= 0",
        )

    base_cols = [
        CitizenReport.report_id,
        CitizenReport.ward_id,
        func.ST_Y(CitizenReport.location).label("lat"),
        func.ST_X(CitizenReport.location).label("lon"),
        CitizenReport.water_depth,
        CitizenReport.image_url,
        CitizenReport.cv_verified,
        CitizenReport.cv_water_depth_m,
        CitizenReport.cv_confidence,
        CitizenReport.description,
        CitizenReport.is_duplicate,
        CitizenReport.duplicate_of_id,
        CitizenReport.operator_verification_status,
        CitizenReport.submitted_at,
        CitizenReportNLPAnalysis.classification.label("nlp_classification"),
        CitizenReportNLPAnalysis.confidence.label("nlp_confidence"),
        CitizenReportNLPAnalysis.urgency_score.label("nlp_urgency_score"),
        CitizenReportNLPAnalysis.is_flood_related.label("nlp_is_flood_related"),
        CitizenReportNLPAnalysis.is_waterlogging.label("nlp_is_waterlogging"),
        CitizenReportNLPAnalysis.is_spam.label("nlp_is_spam"),
        CitizenReportNLPAnalysis.detected_language.label("nlp_detected_language"),
        CitizenReportNLPAnalysis.extracted_depth_m.label("nlp_extracted_depth_m"),
        CitizenReportNLPAnalysis.extracted_landmarks.label("nlp_extracted_landmarks"),
        CitizenReportNLPAnalysis.matched_keywords.label("nlp_matched_keywords"),
        CitizenReportNLPAnalysis.model_version.label("nlp_model_version"),
        CitizenReportNLPAnalysis.provenance.label("nlp_provenance"),
        CitizenReportNLPAnalysis.processed_at.label("nlp_processed_at"),
    ]

    stmt = (
        select(*base_cols)
        .outerjoin(CitizenReportNLPAnalysis, CitizenReportNLPAnalysis.report_id == CitizenReport.report_id)
        .order_by(desc(CitizenReport.submitted_at))
    )

    if ward_id:
        stmt = stmt.where(CitizenReport.ward_id == ward_id)
    if verified_only:
        stmt = stmt.where(CitizenReport.cv_verified.is_(True))
    if water_depth:
        wd = water_depth.lower().strip()
        if wd in ("ankle", "knee", "waist", "submerged"):
            stmt = stmt.where(CitizenReport.water_depth == wd)

    # Count total matching before pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # Apply pagination
    stmt = stmt.offset(offset).limit(limit)
    res = await db.execute(stmt)
    rows = res.all()

    reports = [
        CitizenReportResponse(
            report_id=r.report_id,
            ward_id=r.ward_id,
            latitude=float(r.lat),
            longitude=float(r.lon),
            water_depth=r.water_depth,
            image_url=r.image_url,
            cv_verified=r.cv_verified,
            cv_water_depth_m=r.cv_water_depth_m,
            cv_confidence=r.cv_confidence,
            description=r.description,
            is_duplicate=r.is_duplicate,
            duplicate_of_id=r.duplicate_of_id,
            operator_verification_status=r.operator_verification_status,
            submitted_at=r.submitted_at,
            nlp_analysis=(
                {
                    "classification": r.nlp_classification,
                    "confidence": r.nlp_confidence,
                    "urgency_score": r.nlp_urgency_score,
                    "is_flood_related": r.nlp_is_flood_related,
                    "is_waterlogging": r.nlp_is_waterlogging,
                    "is_spam": r.nlp_is_spam,
                    "detected_language": r.nlp_detected_language,
                    "extracted_depth_m": r.nlp_extracted_depth_m,
                    "extracted_landmarks": r.nlp_extracted_landmarks,
                    "matched_keywords": r.nlp_matched_keywords,
                    "model_version": r.nlp_model_version,
                    "provenance": r.nlp_provenance,
                    "processed_at": r.nlp_processed_at.isoformat() if r.nlp_processed_at else None,
                }
                if r.nlp_classification is not None
                else None
            ),
        )
        for r in rows
    ]

    return CitizenReportListResponse(total=total, reports=reports)


@router.get(
    "/summary",
    response_model=ReportVerificationSummary,
    status_code=status.HTTP_200_OK,
    summary="Get report summary statistics"
)
async def get_reports_summary(db: AsyncSession = Depends(get_db)) -> ReportVerificationSummary:
    """
    Calculates summary telemetry for operator triage.
    """
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)

    # Total reports (all time)
    total_stmt = select(func.count(CitizenReport.id))
    total_res = await db.execute(total_stmt)
    total_reports = total_res.scalar() or 0

    # Reports in last 24h
    total_24h_stmt = select(func.count(CitizenReport.id)).where(
        CitizenReport.submitted_at >= since_24h
    )
    total_24h_res = await db.execute(total_24h_stmt)
    total_24h = total_24h_res.scalar() or 0

    # CV-verified reports (24h)
    verified_stmt = select(func.count(CitizenReport.id)).where(
        CitizenReport.submitted_at >= since_24h,
        CitizenReport.cv_verified.is_(True),
    )
    verified_res = await db.execute(verified_stmt)
    verified_count = verified_res.scalar() or 0

    # Duplicate reports (24h)
    dup_stmt = select(func.count(CitizenReport.id)).where(
        CitizenReport.submitted_at >= since_24h,
        CitizenReport.is_duplicate.is_(True),
    )
    dup_res = await db.execute(dup_stmt)
    dup_count = dup_res.scalar() or 0

    # Severe reports (waist/submerged, 24h)
    severe_stmt = select(func.count(CitizenReport.id)).where(
        CitizenReport.submitted_at >= since_24h,
        CitizenReport.water_depth.in_(["waist", "submerged"]),
    )
    severe_res = await db.execute(severe_stmt)
    sev_count = severe_res.scalar() or 0

    # Ward-wise counts (24h)
    ward_stmt = (
        select(CitizenReport.ward_id, func.count(CitizenReport.id))
        .where(CitizenReport.submitted_at >= since_24h)
        .group_by(CitizenReport.ward_id)
    )
    ward_res = await db.execute(ward_stmt)
    ward_wise = {str(w): int(c) for w, c in ward_res.all() if w is not None}

    # Water-depth distribution (24h)
    depth_stmt = (
        select(CitizenReport.water_depth, func.count(CitizenReport.id))
        .where(CitizenReport.submitted_at >= since_24h)
        .group_by(CitizenReport.water_depth)
    )
    depth_res = await db.execute(depth_stmt)
    depth_dist = {str(d): int(c) for d, c in depth_res.all()}
    status_result = await db.execute(
        select(
            CitizenReport.operator_verification_status,
            func.count(CitizenReport.id),
        ).group_by(CitizenReport.operator_verification_status)
    )
    operator_counts = {str(state): int(count) for state, count in status_result.all()}

    return ReportVerificationSummary(
        total_reports=total_reports,
        total_reports_24h=total_24h,
        cv_verified_count=verified_count,
        flagged_duplicates=dup_count,
        severe_reports=sev_count,
        operator_pending=operator_counts.get("pending", 0),
        operator_confirmed=operator_counts.get("confirmed", 0),
        operator_rejected=operator_counts.get("rejected", 0),
        operator_review_required=operator_counts.get("review_required", 0),
        ward_wise_counts=ward_wise,
        water_depth_distribution=depth_dist,
    )


@router.get(
    "/operator/identity",
    response_model=OperatorIdentityResponse,
    summary="Return the identity associated with the operator bearer token",
)
async def get_operator_identity(
    operator_id: str = Depends(require_verification_operator),
) -> OperatorIdentityResponse:
    return OperatorIdentityResponse(operator_id=operator_id)


@router.get(
    "/operator/queue",
    response_model=OperatorReportQueueResponse,
    status_code=status.HTTP_200_OK,
    summary="List reports awaiting authorized human verification",
)
async def list_operator_verification_queue(
    verification_status: Optional[str] = Query(
        None, pattern="^(pending|confirmed|rejected|review_required)$"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    operator_id: str = Depends(require_verification_operator),
    db: AsyncSession = Depends(get_db),
) -> OperatorReportQueueResponse:
    """Return citizen reports to authenticated operators without changing CV verdicts."""
    del operator_id
    ward_match_count = (
        select(func.count(Ward.id))
        .where(func.ST_Covers(Ward.geom, CitizenReport.location))
        .correlate(CitizenReport)
        .scalar_subquery()
    )
    status_filter = (
        CitizenReport.operator_verification_status == verification_status
        if verification_status
        else CitizenReport.operator_verification_status.in_(("pending", "review_required"))
    )
    stmt = (
        select(
            CitizenReport.report_id,
            CitizenReport.ward_id,
            func.ST_Y(CitizenReport.location).label("lat"),
            func.ST_X(CitizenReport.location).label("lon"),
            CitizenReport.water_depth,
            CitizenReport.image_url,
            CitizenReport.cv_verified,
            CitizenReport.cv_water_depth_m,
            CitizenReport.cv_confidence,
            CitizenReport.description,
            CitizenReport.is_duplicate,
            CitizenReport.duplicate_of_id,
            CitizenReport.operator_verification_status,
            ward_match_count.label("ward_match_count"),
            CitizenReport.submitted_at,
            CitizenReportNLPAnalysis.classification.label("nlp_classification"),
            CitizenReportNLPAnalysis.confidence.label("nlp_confidence"),
            CitizenReportNLPAnalysis.urgency_score.label("nlp_urgency_score"),
            CitizenReportNLPAnalysis.is_flood_related.label("nlp_is_flood_related"),
            CitizenReportNLPAnalysis.is_waterlogging.label("nlp_is_waterlogging"),
            CitizenReportNLPAnalysis.is_spam.label("nlp_is_spam"),
            CitizenReportNLPAnalysis.detected_language.label("nlp_detected_language"),
            CitizenReportNLPAnalysis.extracted_depth_m.label("nlp_extracted_depth_m"),
            CitizenReportNLPAnalysis.extracted_landmarks.label("nlp_extracted_landmarks"),
            CitizenReportNLPAnalysis.matched_keywords.label("nlp_matched_keywords"),
            CitizenReportNLPAnalysis.model_version.label("nlp_model_version"),
            CitizenReportNLPAnalysis.provenance.label("nlp_provenance"),
            CitizenReportNLPAnalysis.processed_at.label("nlp_processed_at"),
        )
        .outerjoin(CitizenReportNLPAnalysis, CitizenReportNLPAnalysis.report_id == CitizenReport.report_id)
        .where(status_filter)
    )
    count_result = await db.execute(
        select(func.count(CitizenReport.report_id)).where(status_filter)
    )
    total = int(count_result.scalar() or 0)
    rows = (
        await db.execute(stmt.order_by(desc(CitizenReport.submitted_at)).offset(offset).limit(limit))
    ).all()
    reports = [
        ReportDetailResponse(
            report_id=row.report_id,
            ward_id=row.ward_id,
            latitude=float(row.lat),
            longitude=float(row.lon),
            water_depth=row.water_depth,
            image_url=row.image_url,
            cv_verified=row.cv_verified,
            cv_water_depth_m=row.cv_water_depth_m,
            cv_confidence=row.cv_confidence,
            description=row.description,
            is_duplicate=row.is_duplicate,
            duplicate_of_id=row.duplicate_of_id,
            operator_verification_status=row.operator_verification_status,
            location_validation_status=(
                "matched"
                if row.ward_match_count == 1
                else "ambiguous_boundary"
                if row.ward_match_count > 1
                else "outside_wards"
            ),
            submitted_at=row.submitted_at,
            nlp_analysis=(
                {
                    "classification": row.nlp_classification,
                    "confidence": row.nlp_confidence,
                    "urgency_score": row.nlp_urgency_score,
                    "is_flood_related": row.nlp_is_flood_related,
                    "is_waterlogging": row.nlp_is_waterlogging,
                    "is_spam": row.nlp_is_spam,
                    "detected_language": row.nlp_detected_language,
                    "extracted_depth_m": row.nlp_extracted_depth_m,
                    "extracted_landmarks": row.nlp_extracted_landmarks,
                    "matched_keywords": row.nlp_matched_keywords,
                    "model_version": row.nlp_model_version,
                    "provenance": row.nlp_provenance,
                    "processed_at": row.nlp_processed_at.isoformat() if row.nlp_processed_at else None,
                }
                if row.nlp_classification is not None
                else None
            ),
        )
        for row in rows
    ]
    return OperatorReportQueueResponse(total=total, reports=reports)


@router.get(
    "/ground-truth/events",
    response_model=FloodEventListResponse,
    status_code=status.HTTP_200_OK,
    summary="List operator-confirmed event candidates",
)
async def list_ground_truth_events(
    source_kind: Optional[str] = Query(None, pattern="^(citizen_report|field_observation|bmc_record)$"),
    include_duplicate_candidates: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    operator_id: str = Depends(require_verification_operator),
    db: AsyncSession = Depends(get_db),
) -> FloodEventListResponse:
    """List confirmed event candidates; citizen records are not marked as BMC-official."""
    del operator_id
    stmt = select(
        FloodEvent,
        func.ST_Y(FloodEvent.location).label("latitude"),
        func.ST_X(FloodEvent.location).label("longitude"),
    ).where(FloodEvent.verification_status == "operator_confirmed")
    count_stmt = select(func.count(FloodEvent.id)).where(
        FloodEvent.verification_status == "operator_confirmed"
    )
    if not include_duplicate_candidates:
        stmt = stmt.where(FloodEvent.is_duplicate.is_(False))
        count_stmt = count_stmt.where(FloodEvent.is_duplicate.is_(False))
    if source_kind:
        stmt = stmt.where(FloodEvent.source_kind == source_kind)
        count_stmt = count_stmt.where(FloodEvent.source_kind == source_kind)
    count_result = await db.execute(count_stmt)
    total = int(count_result.scalar() or 0)
    rows = (
        await db.execute(
            stmt.order_by(desc(FloodEvent.event_timestamp)).offset(offset).limit(limit)
        )
    ).all()
    return FloodEventListResponse(
        total=total,
        events=[
            FloodEventResponse(
                event_id=event.event_id,
                source_kind=event.source_kind,
                source_record_id=event.source_record_id,
                source_url=event.source_url,
                event_timestamp=event.event_timestamp,
                latitude=float(latitude),
                longitude=float(longitude),
                location_validation_status=event.location_validation_status,
                ward_id=event.ward_id,
                water_depth=event.water_depth,
                water_depth_m=event.water_depth_m,
                is_duplicate=event.is_duplicate,
                duplicate_of_report_id=event.duplicate_of_report_id,
                location_description=event.location_description,
                evidence_image_urls=event.evidence_image_urls or [],
                verification_status=event.verification_status,
                verified_by=event.verified_by,
                verified_at=event.verified_at,
                official_confirmation=event.official_confirmation,
                verification_reason=event.verification_reason,
            )
            for event, latitude, longitude in rows
        ],
    )


@router.post(
    "/{report_id}/verification",
    response_model=ReportVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm, reject, or flag a citizen flood report",
)
async def verify_citizen_report(
    report_id: str,
    decision: ReportVerificationRequest,
    operator_id: str = Depends(require_verification_operator),
    db: AsyncSession = Depends(get_db),
) -> ReportVerificationResponse:
    """Record a human decision, an immutable history snapshot, and a distinct event row."""
    report = (
        await db.execute(
            select(CitizenReport)
            .where(CitizenReport.report_id == report_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found.")

    submitted_latitude, submitted_longitude = await _report_coordinates(db, report_id)
    latitude = decision.latitude if decision.latitude is not None else submitted_latitude
    longitude = decision.longitude if decision.longitude is not None else submitted_longitude
    event_timestamp = decision.event_timestamp or report.submitted_at
    water_depth = decision.water_depth or report.water_depth
    ward_id, location_validation_status = await _resolve_unique_ward(
        db, latitude, longitude
    )
    status_for_action = {
        "confirm": "confirmed",
        "reject": "rejected",
        "review": "review_required",
        "resolve": "resolved",
        "expire": "expired",
    }[decision.action]
    event_status = {
        "confirmed": "operator_confirmed",
        "rejected": "rejected",
        "review_required": "review_required",
        "resolved": "resolved",
        "expired": "expired",
    }[status_for_action]

    event = (
        await db.execute(
            select(FloodEvent)
            .where(
                FloodEvent.source_kind == "citizen_report",
                FloodEvent.source_record_id == report.report_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    evidence_urls = await _evidence_urls_for_report(db, report)
    previous_status = report.operator_verification_status
    report.operator_verification_status = status_for_action
    event_id = None

    if event is not None or decision.action == "confirm":
        if event is None:
            event = FloodEvent(
                event_id=str(uuid.uuid4()),
                source_kind="citizen_report",
                source_record_id=report.report_id,
                event_timestamp=event_timestamp,
                location=func.ST_SetSRID(func.ST_Point(longitude, latitude), 4326),
                location_validation_status=location_validation_status,
                verified_by=operator_id,
                verified_at=datetime.now(timezone.utc),
            )
            db.add(event)
        event.event_timestamp = event_timestamp
        event.location = func.ST_SetSRID(func.ST_Point(longitude, latitude), 4326)
        event.location_validation_status = location_validation_status
        event.ward_id = ward_id
        event.water_depth = water_depth
        event.water_depth_m = decision.water_depth_m
        event.is_duplicate = report.is_duplicate
        event.duplicate_of_report_id = report.duplicate_of_id
        event.location_description = report.description
        event.evidence_image_urls = evidence_urls
        event.verification_status = event_status
        event.verified_by = operator_id
        event.verified_at = datetime.now(timezone.utc)
        event.official_confirmation = False
        event.verification_reason = decision.reason
        event_id = event.event_id
        await db.flush()

    history = FloodEventVerificationHistory(
        report_id=report.report_id,
        event_id=event_id,
        operator_id=operator_id,
        action=decision.action,
        previous_status=previous_status,
        new_status=status_for_action,
        reason=decision.reason,
        event_timestamp=event_timestamp,
        latitude=latitude,
        longitude=longitude,
        location_validation_status=location_validation_status,
        ward_id=ward_id,
        water_depth=water_depth,
        water_depth_m=decision.water_depth_m,
        is_duplicate=report.is_duplicate,
        duplicate_of_report_id=report.duplicate_of_id,
        evidence_image_urls=evidence_urls,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(history)
    await db.commit()
    await db.refresh(history)
    return ReportVerificationResponse(
        report_id=report.report_id,
        operator_verification_status=status_for_action,
        event_id=event_id,
        verification_history_id=history.id,
        official_confirmation=False,
    )


@router.get(
    "/{report_id}/verification-history",
    response_model=List[FloodEventVerificationHistoryResponse],
    status_code=status.HTTP_200_OK,
    summary="Read the append-only operator decision history for a report",
)
async def get_report_verification_history(
    report_id: str,
    operator_id: str = Depends(require_verification_operator),
    db: AsyncSession = Depends(get_db),
) -> List[FloodEventVerificationHistoryResponse]:
    del operator_id
    exists = await db.execute(
        select(CitizenReport.id).where(CitizenReport.report_id == report_id)
    )
    if exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found.")
    rows = (
        await db.execute(
            select(FloodEventVerificationHistory)
            .where(FloodEventVerificationHistory.report_id == report_id)
            .order_by(
                FloodEventVerificationHistory.occurred_at,
                FloodEventVerificationHistory.id,
            )
        )
    ).scalars().all()
    return [
        FloodEventVerificationHistoryResponse.model_validate(row)
        for row in rows
    ]


@router.post(
    "/{report_id}/verification-evidence",
    status_code=status.HTTP_201_CREATED,
    summary="Attach photographs to a report's operator verification record",
)
async def add_verification_evidence(
    report_id: str,
    note: str = Form(..., min_length=1, max_length=2000),
    images: List[UploadFile] = File(...),
    operator_id: str = Depends(require_verification_operator),
    db: AsyncSession = Depends(get_db),
):
    """Persist operator evidence images and append an auditable evidence-added record."""
    if len(images) > 5:
        raise HTTPException(status_code=413, detail="At most 5 evidence images may be attached.")
    if not images:
        raise HTTPException(status_code=422, detail="At least one evidence image is required.")
    if not note.strip():
        raise HTTPException(status_code=422, detail="An evidence note is required.")
    report = (
        await db.execute(
            select(CitizenReport)
            .where(CitizenReport.report_id == report_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found.")

    saved_files: List[str] = []
    new_urls: List[str] = []
    total_bytes = 0
    try:
        storage = build_evidence_storage()
        for image in images:
            _validate_image(image)
            remaining_bytes = MAX_IMAGE_SIZE_BYTES - total_bytes
            content = await image.read(remaining_bytes + 1)
            if len(content) > remaining_bytes:
                raise HTTPException(
                    status_code=413,
                    detail="Verification evidence images exceed the 10 MB total limit.",
                )
            total_bytes += len(content)
            if len(content) < 50:
                raise HTTPException(
                    status_code=400,
                    detail="Evidence images must contain at least 50 bytes.",
                )
            _validate_image_payload(image.filename or "", content)
            extension = os.path.splitext(image.filename or "")[1].lower()
            filename = f"{uuid.uuid4().hex}{extension}"
            content_type = (image.content_type or "").lower()
            await asyncio.to_thread(
                storage.save,
                report.report_id,
                filename,
                content,
                content_type,
            )
            saved_files.append(filename)
            new_urls.append(
                f"/v1/reports/{report.report_id}/verification-evidence/{filename}"
            )

        latitude, longitude = await _report_coordinates(db, report_id)
        ward_id, location_validation_status = await _resolve_unique_ward(
            db, latitude, longitude
        )
        event = (
            await db.execute(
                select(FloodEvent)
                .where(
                    FloodEvent.source_kind == "citizen_report",
                    FloodEvent.source_record_id == report.report_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        evidence_urls = await _evidence_urls_for_report(db, report)
        evidence_urls.extend(url for url in new_urls if url not in evidence_urls)
        history = FloodEventVerificationHistory(
            report_id=report.report_id,
            event_id=event.event_id if event else None,
            operator_id=operator_id,
            action="evidence_added",
            previous_status=report.operator_verification_status,
            new_status=report.operator_verification_status,
            reason=note.strip(),
            event_timestamp=event.event_timestamp if event else report.submitted_at,
            latitude=latitude,
            longitude=longitude,
            location_validation_status=(
                event.location_validation_status if event else location_validation_status
            ),
            ward_id=event.ward_id if event else ward_id,
            water_depth=event.water_depth if event else report.water_depth,
            water_depth_m=event.water_depth_m if event else None,
            is_duplicate=report.is_duplicate,
            duplicate_of_report_id=report.duplicate_of_id,
            evidence_image_urls=new_urls,
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(history)
        if event is not None:
            event.evidence_image_urls = evidence_urls
        await db.commit()
        await db.refresh(history)
        logger.info(
            "Operator evidence added: operator=%s report=%s image_count=%s byte_count=%s",
            operator_id,
            report.report_id,
            len(new_urls),
            total_bytes,
        )
        return {
            "report_id": report.report_id,
            "verification_history_id": history.id,
            "evidence_image_urls": new_urls,
        }
    except HTTPException:
        await db.rollback()
        for filename in saved_files:
            try:
                await asyncio.to_thread(storage.delete, report.report_id, filename)
            except Exception:
                logger.exception(
                    "Could not remove uncommitted verification evidence for report %s",
                    report.report_id,
                )
        raise
    except Exception as exc:
        await db.rollback()
        for filename in saved_files:
            try:
                await asyncio.to_thread(storage.delete, report.report_id, filename)
            except Exception:
                logger.exception(
                    "Could not remove uncommitted verification evidence for report %s",
                    report.report_id,
                )
        logger.exception("Failed to save verification evidence for report %s", report_id)
        raise HTTPException(
            status_code=500, detail="Failed to save verification evidence."
        ) from exc


@router.get(
    "/{report_id}/verification-evidence/{filename}",
    status_code=status.HTTP_200_OK,
    summary="Retrieve a private operator verification photograph",
)
async def get_verification_evidence(
    report_id: str,
    filename: str,
    operator_id: str = Depends(require_verification_operator),
    db: AsyncSession = Depends(get_db),
):
    """Serve only evidence associated with this report, and only to an authorized operator."""
    if not re.fullmatch(r"[a-f0-9]{32}\.(jpg|jpeg|png|webp)", filename):
        logger.warning(
            "Operator evidence retrieval rejected: operator=%s report=%s reason=invalid_filename",
            operator_id,
            report_id,
        )
        raise HTTPException(status_code=404, detail="Verification evidence not found.")
    image_url = f"/v1/reports/{report_id}/verification-evidence/{filename}"
    result = await db.execute(
        select(FloodEventVerificationHistory.id).where(
            FloodEventVerificationHistory.report_id == report_id,
            FloodEventVerificationHistory.evidence_image_urls.contains([image_url]),
        ).limit(1)
    )
    if result.scalar_one_or_none() is None:
        logger.warning(
            "Operator evidence retrieval denied: operator=%s report=%s",
            operator_id,
            report_id,
        )
        raise HTTPException(status_code=404, detail="Verification evidence not found.")
    try:
        content = await asyncio.to_thread(
            build_evidence_storage().read,
            report_id,
            filename,
        )
    except FileNotFoundError:
        logger.warning(
            "Operator evidence retrieval missing: operator=%s report=%s",
            operator_id,
            report_id,
        )
        raise HTTPException(status_code=404, detail="Verification evidence not found.")
    except Exception as exc:
        logger.exception(
            "Private evidence storage read failed: operator=%s report=%s",
            operator_id,
            report_id,
        )
        raise HTTPException(status_code=503, detail="Verification evidence is unavailable.") from exc
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    logger.info(
        "Operator evidence retrieved: operator=%s report=%s",
        operator_id,
        report_id,
    )
    return Response(
        content=content,
        media_type=media_types[os.path.splitext(filename)[1]],
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get(
    "/{report_id}",
    response_model=ReportDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single citizen report by its UUID"
)
async def get_citizen_report(
    report_id: str,
    db: AsyncSession = Depends(get_db)
) -> ReportDetailResponse:
    """Retrieve an individual citizen report including CV verification details."""
    stmt = (
        select(
            CitizenReport.report_id,
            CitizenReport.ward_id,
            func.ST_Y(CitizenReport.location).label("lat"),
            func.ST_X(CitizenReport.location).label("lon"),
            CitizenReport.water_depth,
            CitizenReport.image_url,
            CitizenReport.cv_verified,
            CitizenReport.cv_water_depth_m,
            CitizenReport.cv_confidence,
            CitizenReport.description,
            CitizenReport.is_duplicate,
            CitizenReport.duplicate_of_id,
            CitizenReport.operator_verification_status,
            CitizenReport.submitted_at,
            CitizenReportNLPAnalysis.classification.label("nlp_classification"),
            CitizenReportNLPAnalysis.confidence.label("nlp_confidence"),
            CitizenReportNLPAnalysis.urgency_score.label("nlp_urgency_score"),
            CitizenReportNLPAnalysis.is_flood_related.label("nlp_is_flood_related"),
            CitizenReportNLPAnalysis.is_waterlogging.label("nlp_is_waterlogging"),
            CitizenReportNLPAnalysis.is_spam.label("nlp_is_spam"),
            CitizenReportNLPAnalysis.detected_language.label("nlp_detected_language"),
            CitizenReportNLPAnalysis.extracted_depth_m.label("nlp_extracted_depth_m"),
            CitizenReportNLPAnalysis.extracted_landmarks.label("nlp_extracted_landmarks"),
            CitizenReportNLPAnalysis.matched_keywords.label("nlp_matched_keywords"),
            CitizenReportNLPAnalysis.model_version.label("nlp_model_version"),
            CitizenReportNLPAnalysis.provenance.label("nlp_provenance"),
            CitizenReportNLPAnalysis.processed_at.label("nlp_processed_at"),
        )
        .outerjoin(CitizenReportNLPAnalysis, CitizenReportNLPAnalysis.report_id == CitizenReport.report_id)
        .where(CitizenReport.report_id == report_id)
    )

    res = await db.execute(stmt)
    row = res.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found",
        )

    nlp_payload = None
    if row.nlp_classification is not None:
        nlp_payload = {
            "classification": row.nlp_classification,
            "confidence": row.nlp_confidence,
            "urgency_score": row.nlp_urgency_score,
            "is_flood_related": row.nlp_is_flood_related,
            "is_waterlogging": row.nlp_is_waterlogging,
            "is_spam": row.nlp_is_spam,
            "detected_language": row.nlp_detected_language,
            "extracted_depth_m": row.nlp_extracted_depth_m,
            "extracted_landmarks": row.nlp_extracted_landmarks,
            "matched_keywords": row.nlp_matched_keywords,
            "model_version": row.nlp_model_version,
            "provenance": row.nlp_provenance,
            "processed_at": row.nlp_processed_at.isoformat() if row.nlp_processed_at else None,
        }

    return ReportDetailResponse(
        report_id=row.report_id,
        ward_id=row.ward_id,
        latitude=float(row.lat),
        longitude=float(row.lon),
        water_depth=row.water_depth,
        image_url=row.image_url,
        cv_verified=row.cv_verified,
        cv_water_depth_m=row.cv_water_depth_m,
        cv_confidence=row.cv_confidence,
        description=row.description,
        is_duplicate=row.is_duplicate,
        duplicate_of_id=row.duplicate_of_id,
        operator_verification_status=row.operator_verification_status,
        submitted_at=row.submitted_at,
        nlp_analysis=nlp_payload,
    )


@router.post(
    "/cv-test",
    status_code=status.HTTP_200_OK,
    summary="Direct Computer Vision inference test without database persistence",
    tags=["Citizen Reports"]
)
async def test_cv_inference(
    image: UploadFile = File(..., description="Photograph to analyze (JPEG/PNG)"),
    reported_depth: str = Form("knee", description="Optional reported depth: ankle, knee, waist, submerged"),
    return_annotated_image: bool = Form(False, description="Include base64 annotated image with bounding boxes")
):
    """
    Direct prototype/test endpoint for evaluation panels and developers.
    Runs real Ultralytics YOLO inference on the uploaded image and returns:
    - cv_verified: boolean verdict
    - water_detected: boolean
    - cv_confidence: real model detection confidence
    - detected_objects: list of real bounding boxes, class names, confidences
    - cv_water_depth_m: defensible depth estimate in meters (or null)
    - model_version & model_source (custom_flood_model, pretrained_coco, or heuristic_fallback)
    - optional annotated_image_base64
    Does NOT require database persistence.
    """
    _validate_image(image)
    content = await image.read()
    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image too large. Maximum size is {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB.",
        )
    if not content or len(content) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty or too small.",
        )

    analysis = cv_verifier.analyze_image_bytes(content, reported_depth=reported_depth)

    response_data = {
        "is_valid_image": analysis.get("cv_verified", False) or len(analysis.get("detected_objects", [])) > 0 or analysis.get("water_detected", False),
        "cv_verified": analysis.get("cv_verified", False),
        "water_detected": analysis.get("water_detected", False),
        "cv_confidence": analysis.get("cv_confidence", 0.0),
        "detected_objects": analysis.get("detected_objects", []),
        "detected_landmarks": analysis.get("detected_landmarks", []),
        "cv_water_depth_m": analysis.get("cv_water_depth_m"),
        "reported_water_depth": analysis.get("reported_water_depth", reported_depth),
        "cv_estimated_depth_category": analysis.get("cv_estimated_depth_category"),
        "model_version": analysis.get("model_version"),
        "model_source": analysis.get("model_source"),
        "inference_time_ms": analysis.get("inference_time_ms"),
        "reason": analysis.get("reason"),
    }

    if return_annotated_image:
        import base64
        annotated_bytes = cv_verifier.yolo.generate_annotated_image(
            content, analysis.get("detected_objects", [])
        )
        response_data["annotated_image_base64"] = base64.b64encode(annotated_bytes).decode("utf-8")

    return response_data


@router.post(
    "/{report_id}/reprocess-nlp",
    response_model=ReportDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Reprocess citizen report description through Engine B NLP pipeline",
)
async def reprocess_citizen_report_nlp(
    report_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReportDetailResponse:
    """
    Rerun Engine B NLP analysis on a report's original description.
    Updates or inserts the corresponding citizen_report_nlp_analysis row.
    Original citizen description and citizen-reported depth are strictly preserved.
    """
    report = (
        await db.execute(
            select(CitizenReport)
            .where(CitizenReport.report_id == report_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found.")

    depth_category_m = {
        "ankle": 0.15,
        "knee": 0.50,
        "waist": 1.00,
        "submerged": 1.80,
    }.get(report.water_depth.lower().strip(), 0.3)

    nlp_result = citizen_nlp.analyze_report_text(
        report.description,
        reported_category="waterlogging",
        reported_depth_m=depth_category_m,
    )

    existing_nlp = (
        await db.execute(
            select(CitizenReportNLPAnalysis)
            .where(CitizenReportNLPAnalysis.report_id == report_id)
            .with_for_update()
        )
    ).scalar_one_or_none()

    now_utc = datetime.now(timezone.utc)
    if existing_nlp is not None:
        existing_nlp.model_version = nlp_result["model_version"]
        existing_nlp.classification = nlp_result["classification"]
        existing_nlp.confidence = nlp_result["confidence"]
        existing_nlp.urgency_score = nlp_result["urgency_score"]
        existing_nlp.is_flood_related = nlp_result["is_flood_related"]
        existing_nlp.is_waterlogging = nlp_result["is_waterlogging"]
        existing_nlp.is_spam = nlp_result["is_spam"]
        existing_nlp.detected_language = nlp_result["detected_language"]
        existing_nlp.extracted_depth_m = nlp_result["extracted_depth_m"]
        existing_nlp.extracted_landmarks = nlp_result["extracted_landmarks"]
        existing_nlp.matched_keywords = nlp_result["matched_keywords"]
        existing_nlp.provenance = nlp_result["provenance"]
        existing_nlp.processed_at = now_utc
    else:
        new_nlp = CitizenReportNLPAnalysis(
            report_id=report.report_id,
            model_version=nlp_result["model_version"],
            classification=nlp_result["classification"],
            confidence=nlp_result["confidence"],
            urgency_score=nlp_result["urgency_score"],
            is_flood_related=nlp_result["is_flood_related"],
            is_waterlogging=nlp_result["is_waterlogging"],
            is_spam=nlp_result["is_spam"],
            detected_language=nlp_result["detected_language"],
            extracted_depth_m=nlp_result["extracted_depth_m"],
            extracted_landmarks=nlp_result["extracted_landmarks"],
            matched_keywords=nlp_result["matched_keywords"],
            provenance=nlp_result["provenance"],
            processed_at=now_utc,
        )
        db.add(new_nlp)

    await db.commit()
    return await get_citizen_report(report_id, db=db)
