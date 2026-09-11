# Placeholder for backend/api/routes/alerts.py
"""
Emergency alert broadcast and CAP v1.2 distribution endpoints.
"""

import uuid
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_db
from backend.models.ward import Ward
from backend.models.alert import AlertDispatched
from backend.schemas.alert import (
    AlertCreate,
    AlertResponse,
    AlertListResponse,
    WebPushSubscription,
)
from backend.pipeline.cap_builder import cap_builder
from backend.pipeline.alert_dispatcher import alert_dispatcher

router = APIRouter(prefix="/alerts", tags=["Emergency Alerts"])


@router.post(
    "",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a new emergency flood alert across CAP v1.2, WhatsApp, and Web Push"
)
async def publish_emergency_alert(
    payload: AlertCreate,
    db: AsyncSession = Depends(get_db)
) -> AlertResponse:
    """
    Publish an emergency alert bulletin:
    1. Validates ward existence
    2. Generates multi-lingual translations (EN, MR, HI)
    3. Builds OASIS CAP v1.2 XML document
    4. Dispatches to selected delivery channels (WhatsApp / Push / CAP)
    5. Persists alert record with audit details
    """
    ward_stmt = select(Ward).where(Ward.ward_id == payload.ward_id)
    ward_res = await db.execute(ward_stmt)
    ward = ward_res.scalar_one_or_none()

    if not ward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ward '{payload.ward_id}' not found."
        )

    alert_id = str(uuid.uuid4())[:8].upper()

    # 1. Localize into English, Marathi, Hindi
    translations = alert_dispatcher.generate_translations(
        ward_name=ward.ward_name,
        severity=payload.severity,
        headline=payload.headline,
        instruction=payload.instruction
    )

    # 2. Build CAP v1.2 XML
    cap_xml = cap_builder.generate_cap_xml(
        alert_id=alert_id,
        ward_id=ward.ward_id,
        ward_name=ward.ward_name,
        severity_tier=payload.severity,
        headline=payload.headline,
        instruction=payload.instruction,
        translations=translations
    )

    # 3. Disseminate via channels
    recipients_count = 0
    if payload.channel in ("whatsapp", "all"):
        # Format WhatsApp message with trilingual alerts
        wa_msg = (
            f"🚨 *BMC FLOOD ALERT: {ward.ward_name.upper()}*\n"
            f"Severity: {payload.severity.upper()}\n\n"
            f"EN: {translations['en']['headline']}\n"
            f"Action: {translations['en']['instruction']}\n\n"
            f"MR: {translations['mr']['headline']}\n"
            f"सूचना: {translations['mr']['instruction']}\n\n"
            f"Toll Free: 1916 / Mumbai Disaster Management Unit"
        )
        await alert_dispatcher.dispatch_whatsapp_message("+919999999999", wa_msg)
        recipients_count += 1250

    if payload.channel in ("push", "all"):
        await alert_dispatcher.dispatch_web_push({
            "title": f"🚨 Flood Warning: {ward.ward_name}",
            "body": payload.headline
        })
        recipients_count += 840

    # 4. Save to Database
    alert = AlertDispatched(
        alert_id=f"ALT-{alert_id}",
        ward_id=ward.ward_id,
        severity=payload.severity,
        channel=payload.channel,
        headline=payload.headline,
        message_text=translations["en"]["description"],
        cap_xml=cap_xml,
        recipients_count=recipients_count,
        language_translations=translations,
        dispatched_at=datetime.now(timezone.utc)
    )
    db.add(alert)
    await db.commit()

    return AlertResponse.model_validate(alert)


@router.get(
    "",
    response_model=AlertListResponse,
    status_code=status.HTTP_200_OK,
    summary="List chronological history of dispatched emergency bulletins"
)
async def list_alerts(
    ward_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
) -> AlertListResponse:
    """
    List alerts filtered by ward or latest broadcast time.
    """
    stmt = (
        select(AlertDispatched)
        .order_by(desc(AlertDispatched.dispatched_at))
        .limit(limit)
    )
    if ward_id:
        stmt = stmt.where(AlertDispatched.ward_id == ward_id)

    res = await db.execute(stmt)
    alerts = res.scalars().all()

    items = [AlertResponse.model_validate(a) for a in alerts]
    return AlertListResponse(total=len(items), alerts=items)


@router.get(
    "/{alert_id}/cap.xml",
    status_code=status.HTTP_200_OK,
    summary="Download or view standard OASIS CAP v1.2 XML document for an alert"
)
async def get_cap_xml(
    alert_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns standard OASIS CAP v1.2 XML payload with application/xml media type
    for syndication with NDMA and SACHET systems.
    """
    stmt = select(AlertDispatched).where(AlertDispatched.alert_id == alert_id)
    res = await db.execute(stmt)
    alert = res.scalar_one_or_none()

    if not alert or not alert.cap_xml:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CAP XML document for alert '{alert_id}' not found."
        )

    return Response(content=alert.cap_xml, media_type="application/xml")
