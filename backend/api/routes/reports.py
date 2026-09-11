"""
API endpoints for crowdsourced citizen flood report intake, duplicate deduplication,
and Computer Vision image verification.
"""

import os
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy import select, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_GeomFromText, ST_DWithin, ST_Contains, ST_SetSRID, ST_Point, ST_X, ST_Y

from backend.models.database import get_db
from backend.models.report import CitizenReport
from backend.models.ward import Ward
from backend.schemas.report import (
    CitizenReportResponse,
    CitizenReportListResponse,
    ReportVerificationSummary,
)
from backend.ml.engine_b.cv_water_depth import cv_verifier

router = APIRouter(prefix="/reports", tags=["Citizen Reports"])

# Local uploads directory fallback if S3/Cloudinary credentials aren't active in dev
UPLOAD_DIR = "/tmp/flood_reports"
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    if water_depth.lower() not in ("ankle", "knee", "waist", "submerged"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="water_depth must be one of: ankle, knee, waist, submerged"
        )

    report_id = str(uuid.uuid4())
    point_geom = f"SRID=4326;POINT({longitude} {latitude})"

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
            50.0  # 50 meters
        ),
        CitizenReport.submitted_at >= fifteen_min_ago
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
        content = await image.read()
        file_ext = os.path.splitext(image.filename or "report.jpg")[1] or ".jpg"
        file_path = os.path.join(UPLOAD_DIR, f"{report_id}{file_ext}")
        with open(file_path, "wb") as f:
            f.write(content)
        image_url = f"/uploads/{report_id}{file_ext}"

        # Analyze using Engine B
        analysis = cv_verifier.analyze_image_bytes(content, reported_depth=water_depth)
        cv_verified = analysis.get("cv_verified", False)
        cv_depth_m = analysis.get("cv_water_depth_m")
        cv_conf = analysis.get("cv_confidence")
    else:
        # Default estimation without image
        depth_defaults = {"ankle": 0.15, "knee": 0.50, "waist": 1.0, "submerged": 1.8}
        cv_depth_m = depth_defaults.get(water_depth.lower(), 0.3)
        cv_conf = 0.5

    # 4. Save to database
    report = CitizenReport(
        report_id=report_id,
        ward_id=resolved_ward_id,
        location=func.ST_SetSRID(func.ST_Point(longitude, latitude), 4326),
        water_depth=water_depth.lower(),
        image_url=image_url,
        cv_verified=cv_verified,
        cv_water_depth_m=cv_depth_m,
        cv_confidence=cv_conf,
        description=description,
        is_duplicate=is_dup,
        duplicate_of_id=duplicate_of,
        submitted_at=datetime.now(timezone.utc)
    )
    db.add(report)
    await db.commit()

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
        submitted_at=report.submitted_at
    )


@router.get(
    "",
    response_model=CitizenReportListResponse,
    status_code=status.HTTP_200_OK,
    summary="List citizen reports with optional ward filter and verification flags"
)
async def list_citizen_reports(
    ward_id: Optional[str] = None,
    verified_only: bool = False,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
) -> CitizenReportListResponse:
    """
    Retrieve incident reports ordered chronologically by submission time.
    """
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
            CitizenReport.submitted_at
        )
        .order_by(desc(CitizenReport.submitted_at))
        .limit(limit)
    )

    if ward_id:
        stmt = stmt.where(CitizenReport.ward_id == ward_id)
    if verified_only:
        stmt = stmt.where(CitizenReport.cv_verified.is_(True))

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
            submitted_at=r.submitted_at
        )
        for r in rows
    ]

    return CitizenReportListResponse(total=len(reports), reports=reports)


@router.get(
    "/summary",
    response_model=ReportVerificationSummary,
    status_code=status.HTTP_200_OK,
    summary="Get 24-hour verification and triage summary metrics"
)
async def get_reports_summary(db: AsyncSession = Depends(get_db)) -> ReportVerificationSummary:
    """
    Calculates summary telemetry for operator triage.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    total_stmt = select(func.count(CitizenReport.id)).where(CitizenReport.submitted_at >= since)
    total_res = await db.execute(total_stmt)
    total_24h = total_res.scalar() or 0

    verified_stmt = select(func.count(CitizenReport.id)).where(
        CitizenReport.submitted_at >= since,
        CitizenReport.cv_verified.is_(True)
    )
    ver_res = await db.execute(verified_stmt)
    verified_count = ver_res.scalar() or 0

    dup_stmt = select(func.count(CitizenReport.id)).where(
        CitizenReport.submitted_at >= since,
        CitizenReport.is_duplicate.is_(True)
    )
    dup_res = await db.execute(dup_stmt)
    dup_count = dup_res.scalar() or 0

    severe_stmt = select(func.count(CitizenReport.id)).where(
        CitizenReport.submitted_at >= since,
        CitizenReport.water_depth.in_(["waist", "submerged"])
    )
    sev_res = await db.execute(severe_stmt)
    sev_count = sev_res.scalar() or 0

    return ReportVerificationSummary(
        total_reports_24h=total_24h,
        cv_verified_count=verified_count,
        flagged_duplicates=dup_count,
        severe_reports=sev_count
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
    content = await image.read()
    if not content or len(content) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty or too small."
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

