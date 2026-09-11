"""
Social media intelligence ingestion and stream processing pipeline.
Ingests from X/Twitter API, Telegram disaster channels, and BMC 1916 Helpline,
runs Engine C NLP classification, and populates the operational data cache.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.social import SocialSignal
from backend.models.ward import Ward
from backend.ml.engine_c.nlp_classifier import nlp_classifier

logger = logging.getLogger("fip.social_ingest")
settings = get_settings()

SAMPLE_SIMULATION_POSTS = [
    {
        "source": "twitter",
        "author_handle": "@MumbaiRainLive",
        "content_text": "Waterlogging reported at Hindmata Cinema and Dadar TT Circle. Water level above knee height. Avoid Dr Babasaheb Ambedkar Road.",
        "posted_at": datetime.now(timezone.utc)
    },
    {
        "source": "telegram",
        "author_handle": "@BMC_Ward_Alerts",
        "content_text": "अतिदक्षता: कुर्ला कमानी आणि बैल बाजार परिसरात नाला ओसंडून वाहत आहे. घरात पाणी शिरले असून मदतीची गरज आहे! जीव वाचवा!",
        "posted_at": datetime.now(timezone.utc)
    },
    {
        "source": "helpline_1916",
        "author_handle": "Citizen-Helpline-9820",
        "content_text": "Milan subway closed due to 4 feet water. 2 BEST buses stalled inside subway. Immediate evacuation needed.",
        "posted_at": datetime.now(timezone.utc)
    },
    {
        "source": "twitter",
        "author_handle": "@DharaviTimes",
        "content_text": "Mithi river water level rising dangerously near Kranti Nagar. Slum dwellers moving to upper floors. Urgent boats requested.",
        "posted_at": datetime.now(timezone.utc)
    },
    {
        "source": "twitter",
        "author_handle": "@Mumbaikar_99",
        "content_text": "Gandhi Market Sion completely flooded. King's Circle traffic halted. Heavy rains non-stop for last 3 hours.",
        "posted_at": datetime.now(timezone.utc)
    },
    {
        "source": "telegram",
        "author_handle": "@Mumbai_Updates",
        "content_text": "अंधेरी सबवे पाण्याखाली. वेस्टर्न एक्सप्रेस हायवेवर प्रचंड ट्रॅफिक जाम. पाऊस सतत सुरू.",
        "posted_at": datetime.now(timezone.utc)
    }
]


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

    async def ingest_simulation_batch(self, db: AsyncSession) -> List[SocialSignal]:
        """
        Seeds initial realistic flood social signals for testing and demonstration.
        """
        created = []
        for post in SAMPLE_SIMULATION_POSTS:
            sig = await self.process_and_store_signal(
                db=db,
                source=post["source"],
                content_text=post["content_text"],
                author_handle=post["author_handle"],
                posted_at=post["posted_at"]
            )
            created.append(sig)
        return created


social_ingest_pipeline = SocialIngestPipeline()
