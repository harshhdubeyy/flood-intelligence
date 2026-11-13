"""Social media NLP processing and derived artifact pipeline."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ml.engine_c.nlp_classifier import nlp_classifier
from backend.models.social_media_post import SocialMediaPost, SocialPostDerivedArtifact

logger = logging.getLogger("fip.social.nlp")


class SocialNLPProcessingService:
    """
    Applies multilingual Engine C NLP classification to collected social media posts
    and persists verifiable derived artifacts into `social_post_derived_artifacts`.
    """

    async def process_post(
        self,
        db: AsyncSession,
        post: SocialMediaPost,
        reprocess: bool = False,
    ) -> Dict[str, Any]:
        """Process a single social post through Engine C NLP and persist the artifact."""
        if not reprocess:
            existing = await db.execute(
                select(SocialPostDerivedArtifact).where(
                    SocialPostDerivedArtifact.social_post_id == post.id,
                    SocialPostDerivedArtifact.artifact_type == "nlp",
                )
            )
            artifact = existing.scalar_one_or_none()
            if artifact is not None:
                return artifact.payload

        classification_res = nlp_classifier.classify_text(
            post.text_content, explicit_ward=post.ward_id
        )

        artifact_payload = {
            "model_version": classification_res["model_version"],
            "classification": classification_res["classification"],
            "confidence": classification_res["confidence"],
            "urgency_score": classification_res["urgency_score"],
            "is_flood_related": classification_res["is_flood_related"],
            "is_waterlogging": classification_res["is_waterlogging"],
            "detected_language": classification_res["language"],
            "extracted_landmarks": classification_res["extracted_landmarks"],
            "location_name": classification_res["location_name"],
            "mapped_ward_id": classification_res["ward_id"],
            "explanation": classification_res["explanation"],
            "processed_at": classification_res["processed_at"],
            "provenance": classification_res["provenance"],
        }

        # Delete any previous NLP artifact if reprocessing
        await db.execute(
            delete(SocialPostDerivedArtifact).where(
                SocialPostDerivedArtifact.social_post_id == post.id,
                SocialPostDerivedArtifact.artifact_type == "nlp",
            )
        )

        db.add(
            SocialPostDerivedArtifact(
                social_post_id=post.id,
                artifact_type="nlp",
                payload=artifact_payload,
                created_at=datetime.now(timezone.utc),
            )
        )

        # Update processing status on the post if appropriate
        if post.processing_status == "collected":
            post.processing_status = "nlp_processed"

        # Update post ward_id if unresolved and NLP has high-confidence landmark mapping
        if (
            post.ward_id is None
            and classification_res["ward_id"] is not None
            and classification_res["confidence"] >= 0.80
        ):
            post.ward_id = classification_res["ward_id"]
            post.geolocation_confidence = classification_res["confidence"]
            post.ward_assignment_provenance = "nlp_gazetteer_extracted"

        await db.flush()
        return artifact_payload

    async def process_unprocessed_posts(
        self, db: AsyncSession, limit: int = 50
    ) -> Dict[str, Any]:
        """Batch process collected posts that lack an NLP derived artifact."""
        existing_subquery = select(SocialPostDerivedArtifact.social_post_id).where(
            SocialPostDerivedArtifact.artifact_type == "nlp"
        )
        posts_res = await db.execute(
            select(SocialMediaPost)
            .where(
                SocialMediaPost.id.not_in(existing_subquery),
                SocialMediaPost.source_status.in_(("unverified", "current")),
                SocialMediaPost.text_content.is_not(None),
            )
            .limit(limit)
        )
        posts = posts_res.scalars().all()
        processed_count = 0
        for post in posts:
            await self.process_post(db, post)
            processed_count += 1

        if processed_count > 0:
            await db.commit()

        return {
            "processed_count": processed_count,
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


social_nlp_service = SocialNLPProcessingService()
