# Placeholder for backend/api/routes/wards.py
"""
Ward-level endpoints for GIS map layers, metadata, and risk telemetry.
"""

import json
from datetime import datetime, timezone, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_db
from backend.models.ward import Ward
from backend.models.risk import WardRiskScore
from backend.schemas.ward import (
    WardResponse,
    GeoJSONFeatureCollection,
    GeoJSONFeature,
    GeoJSONGeometry,
    WardGeoJSONProperties,
    WardRiskHistoryResponse,
    WardRiskItem,
)

router = APIRouter(prefix="/wards", tags=["Wards"])


@router.get(
    "/geojson",
    response_model=GeoJSONFeatureCollection,
    status_code=status.HTTP_200_OK,
    summary="Retrieve GeoJSON FeatureCollection of all Mumbai wards with active risk scores"
)
async def get_wards_geojson(db: AsyncSession = Depends(get_db)) -> GeoJSONFeatureCollection:
    """
    Fetch all Mumbai wards serialized as RFC 7946 GeoJSON.
    Includes current risk classification and drainage metadata for Mapbox / Deck.gl rendering.
    """
    # Query wards along with their geometry parsed to GeoJSON via PostGIS ST_AsGeoJSON
    stmt = (
        select(
            Ward.id,
            Ward.ward_id,
            Ward.ward_name,
            Ward.city,
            Ward.area_sqkm,
            Ward.population,
            Ward.is_coastal,
            Ward.avg_elevation_m,
            Ward.drainage_index,
            func.ST_AsGeoJSON(Ward.geom).label("geojson_geom")
        )
        .order_by(Ward.ward_id.asc())
    )
    result = await db.execute(stmt)
    ward_rows = result.all()

    if not ward_rows:
        return GeoJSONFeatureCollection(features=[])

    features: List[GeoJSONFeature] = []

    for row in ward_rows:
        raw_geom_json = json.loads(row.geojson_geom) if row.geojson_geom else {"type": "MultiPolygon", "coordinates": []}

        # Query the latest risk score for this ward if available
        risk_stmt = (
            select(WardRiskScore)
            .where(WardRiskScore.ward_id == row.ward_id)
            .order_by(desc(WardRiskScore.computed_at))
            .limit(1)
        )
        risk_res = await db.execute(risk_stmt)
        latest_risk = risk_res.scalar_one_or_none()

        risk_score = float(latest_risk.risk_score) if latest_risk else 0.15
        risk_class = str(latest_risk.risk_class) if latest_risk else "low"
        computed_at = latest_risk.computed_at if latest_risk else datetime.now(timezone.utc)

        properties = WardGeoJSONProperties(
            ward_id=row.ward_id,
            ward_name=row.ward_name,
            city=row.city,
            area_sqkm=row.area_sqkm,
            population=row.population,
            is_coastal=row.is_coastal,
            avg_elevation_m=row.avg_elevation_m,
            drainage_index=row.drainage_index,
            risk_score=risk_score,
            risk_class=risk_class,  # type: ignore
            computed_at=computed_at
        )

        features.append(
            GeoJSONFeature(
                type="Feature",
                id=row.ward_id,
                geometry=GeoJSONGeometry(
                    type=raw_geom_json.get("type", "MultiPolygon"),
                    coordinates=raw_geom_json.get("coordinates", [])
                ),
                properties=properties
            )
        )

    return GeoJSONFeatureCollection(type="FeatureCollection", features=features)


@router.get(
    "",
    response_model=List[WardResponse],
    status_code=status.HTTP_200_OK,
    summary="List all Mumbai administrative wards with current risk scores"
)
async def list_wards(db: AsyncSession = Depends(get_db)) -> List[WardResponse]:
    """
    List all wards with summary statistics and active risk classifications.
    """
    stmt = select(Ward).order_by(Ward.ward_id.asc())
    result = await db.execute(stmt)
    wards = result.scalars().all()

    responses: List[WardResponse] = []
    for w in wards:
        # Get latest risk score
        risk_stmt = (
            select(WardRiskScore)
            .where(WardRiskScore.ward_id == w.ward_id)
            .order_by(desc(WardRiskScore.computed_at))
            .limit(1)
        )
        risk_res = await db.execute(risk_stmt)
        latest_risk = risk_res.scalar_one_or_none()

        responses.append(
            WardResponse(
                id=w.id,
                ward_id=w.ward_id,
                ward_name=w.ward_name,
                city=w.city,
                area_sqkm=w.area_sqkm,
                population=w.population,
                is_coastal=w.is_coastal,
                avg_elevation_m=w.avg_elevation_m,
                drainage_index=w.drainage_index,
                current_risk_score=latest_risk.risk_score if latest_risk else 0.15,
                current_risk_class=latest_risk.risk_class if latest_risk else "low"  # type: ignore
            )
        )

    return responses


@router.get(
    "/{ward_id}",
    response_model=WardResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve details for a specific ward by ward_id"
)
async def get_ward_detail(ward_id: str, db: AsyncSession = Depends(get_db)) -> WardResponse:
    """
    Retrieve single ward specifications and current risk status.
    """
    stmt = select(Ward).where(Ward.ward_id == ward_id)
    res = await db.execute(stmt)
    ward = res.scalar_one_or_none()

    if not ward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ward with identifier '{ward_id}' not found."
        )

    risk_stmt = (
        select(WardRiskScore)
        .where(WardRiskScore.ward_id == ward_id)
        .order_by(desc(WardRiskScore.computed_at))
        .limit(1)
    )
    risk_res = await db.execute(risk_stmt)
    latest_risk = risk_res.scalar_one_or_none()

    return WardResponse(
        id=ward.id,
        ward_id=ward.ward_id,
        ward_name=ward.ward_name,
        city=ward.city,
        area_sqkm=ward.area_sqkm,
        population=ward.population,
        is_coastal=ward.is_coastal,
        avg_elevation_m=ward.avg_elevation_m,
        drainage_index=ward.drainage_index,
        current_risk_score=latest_risk.risk_score if latest_risk else 0.15,
        current_risk_class=latest_risk.risk_class if latest_risk else "low"  # type: ignore
    )


@router.get(
    "/{ward_id}/risk",
    response_model=WardRiskHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current risk score and 24-hour historical progression for a ward"
)
async def get_ward_risk_history(
    ward_id: str,
    db: AsyncSession = Depends(get_db)
) -> WardRiskHistoryResponse:
    """
    Fetch 24-hour time series of 15-minute ML risk scores for sparklines and analysis.
    """
    ward_stmt = select(Ward).where(Ward.ward_id == ward_id)
    res = await db.execute(ward_stmt)
    ward = res.scalar_one_or_none()

    if not ward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ward with identifier '{ward_id}' not found."
        )

    since_time = datetime.now(timezone.utc) - timedelta(hours=24)
    history_stmt = (
        select(WardRiskScore)
        .where(WardRiskScore.ward_id == ward_id, WardRiskScore.computed_at >= since_time)
        .order_by(desc(WardRiskScore.computed_at))
    )
    hist_res = await db.execute(history_stmt)
    history_rows = hist_res.scalars().all()

    current_score = history_rows[0].risk_score if history_rows else 0.15
    current_class = history_rows[0].risk_class if history_rows else "low"

    return WardRiskHistoryResponse(
        ward_id=ward.ward_id,
        ward_name=ward.ward_name,
        current_score=current_score,
        current_class=current_class,
        history_24h=[
            WardRiskItem(
                risk_score=h.risk_score,
                risk_class=h.risk_class,
                model_version=h.model_version,
                computed_at=h.computed_at,
                inputs_json=h.inputs_json
            )
            for h in history_rows
        ]
    )
