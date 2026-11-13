"""Legacy classifier for previously stored SocialSignal records.

Public collection is implemented separately and does not invoke this module.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.social import SocialSignal
from backend.models.ward import Ward
from backend.ml.engine_c.nlp_classifier import nlp_classifier

class SocialIngestPipeline:
    """
    Ingestion orchestrator for social media posts.
    """

    async def process_and_store_signal(
        self,
        db: AsyncSession,
        source: str,
        content_text: str,
        author_handle: Optional[str] = None,
        language: Optional[str] = "auto",
        ward_id: Optional[str] = None,
        location_name: Optional[str] = None,
        posted_at: Optional[datetime] = None
    ) -> SocialSignal:
        """
        Runs Engine C classification, resolves ward if missing, and saves to database.
        """
        # Run ML classification
        nlp_res = nlp_classifier.classify_text(
            text=content_text,
            explicit_ward=ward_id
        )

        final_lang = nlp_res["language"] if language in (None, "auto") else language
        final_ward = ward_id or nlp_res["ward_id"]
        final_location = location_name or nlp_res["location_name"]

        # If ward still unknown, fallback or leave null
        if final_ward:
            # Verify ward exists
            w_res = await db.execute(select(Ward).where(Ward.ward_id == final_ward))
            if not w_res.scalar_one_or_none():
                final_ward = None

        signal = SocialSignal(
            signal_id=f"SOC-{uuid.uuid4().hex[:10].upper()}",
            source=source,
            author_handle=author_handle,
            content_text=content_text,
            language=final_lang,
            ward_id=final_ward,
            location_name=final_location,
            classification=nlp_res["classification"],
            urgency_score=nlp_res["urgency_score"],
            confidence=nlp_res["confidence"],
            extracted_landmarks=nlp_res["extracted_landmarks"],
            posted_at=posted_at or datetime.now(timezone.utc),
            ingested_at=datetime.now(timezone.utc)
        )

        db.add(signal)
        await db.commit()
        await db.refresh(signal)

        # Update Redis cache for fast feature-builder lookup
        #if final_ward:
         #   try:
          #      r = await get_redis()
           #     if r:
            #        await r.set(
             #           f"fip:social:urgency:{final_ward}",
              #          str(nlp_res["urgency_score"]),
               #         ex=1800  # 30 min TTL
                #    )
                 #   await r.incr(f"fip:social:count:{final_ward}")
                  #  await r.expire(f"fip:social:count:{final_ward}", 1800)
            #except Exception as e:
                #logger.debug(f"Redis social update error: {e}")

        return signal

social_ingest_pipeline = SocialIngestPipeline()
