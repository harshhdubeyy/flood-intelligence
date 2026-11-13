"""
Comprehensive unit and integration tests for Phase 10.2:
NLP Flood Intelligence Integration across Citizen Reports and Social Pipelines.
"""

import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import select, func

from backend.ml.engine_b.nlp_pipeline import citizen_nlp, CitizenReportNLP
from backend.ml.engine_c.nlp_classifier import nlp_classifier, SocialNLPClassifier
from backend.models.database import async_session_factory
from backend.models.report import CitizenReport, CitizenReportNLPAnalysis
from backend.models.social_media_post import SocialMediaPost, SocialPostDerivedArtifact
from backend.pipeline.social_nlp import social_nlp_service
from backend.services.report_intelligence import ReportIntelligenceEngine


# ---------------------------------------------------------------------------
# 1. CitizenReportNLP Unit Tests
# ---------------------------------------------------------------------------

def test_citizen_nlp_multilingual_language_detection():
    # English
    assert citizen_nlp.detect_language("Severe waterlogging near Dadar station") == "en"
    # Marathi
    assert citizen_nlp.detect_language("हिंदमाता येथे गुडघाभर पाणी साचले आहे रस्ता बंद") == "mr"
    # Hindi
    assert citizen_nlp.detect_language("कुर्ला में भारी बारिश से कमर तक पानी भर गया है") == "hi"
    # Empty or English fallback
    assert citizen_nlp.detect_language("12345 !!!") == "en"


def test_citizen_nlp_empty_and_short_descriptions():
    res_none = citizen_nlp.analyze_report_text(None)
    assert res_none["classification"] == "noise"
    assert res_none["urgency_score"] == 0.10
    assert res_none["nlp_verified"] is False
    assert res_none["extracted_depth_m"] is None
    assert "heuristic_indic_lexical" in res_none["provenance"]["method"]

    res_short = citizen_nlp.analyze_report_text("hi")
    assert res_short["classification"] == "noise"
    assert res_short["extracted_depth_m"] is None


def test_citizen_nlp_spam_detection():
    spam_samples = [
        "Click here for free bitcoin and casino loans test test",
        "Subscribe now for cheap crypto discount code buy now",
        "Hello world hello world click here",
    ]
    for text in spam_samples:
        res = citizen_nlp.analyze_report_text(text)
        assert res["is_spam"] is True
        assert res["classification"] == "spam"
        assert res["credibility_score"] <= 0.10
        assert res["nlp_verified"] is False
        assert res["urgency_score"] == 0.0


def test_citizen_nlp_english_depth_and_urgency():
    # Ankle
    res_ankle = citizen_nlp.analyze_report_text("Ankle deep waterlogging on SV road near Milan subway")
    assert res_ankle["is_flood_related"] is True
    assert res_ankle["is_waterlogging"] is True
    assert res_ankle["extracted_depth_m"] == 0.15
    assert "Milan Subway" in res_ankle["extracted_landmarks"]

    # Knee
    res_knee = citizen_nlp.analyze_report_text("Knee deep water near King's Circle, traffic stalled")
    assert res_knee["extracted_depth_m"] == 0.50
    assert "King's Circle" in res_knee["extracted_landmarks"]

    # Waist / Urgent
    res_waist = citizen_nlp.analyze_report_text("Waist deep water rising fast near Gandhi Market, cars submerged")
    assert res_waist["classification"] == "urgent"
    assert res_waist["urgency_score"] >= 0.70
    assert res_waist["extracted_depth_m"] == 1.00

    # Evacuation needed
    res_evac = citizen_nlp.analyze_report_text("People trapped on roof, submerged house, need immediate rescue boat in Kurla")
    assert res_evac["classification"] == "evacuation_needed"
    assert res_evac["urgency_score"] >= 0.90
    assert res_evac["confidence"] >= 0.85


def test_citizen_nlp_marathi_depth_and_urgency():
    # Marathi knee depth and waterlogging
    mr_text = "हिंदमाता येथे गुडघाभर पाणी साचले आहे, वाहतूक पूर्ण ठप्प"
    res = citizen_nlp.analyze_report_text(mr_text)
    assert res["detected_language"] == "mr"
    assert res["is_flood_related"] is True
    assert res["is_waterlogging"] is True
    assert res["extracted_depth_m"] == 0.50
    assert "Hindmata" in res["extracted_landmarks"]

    # Marathi evacuation
    mr_evac = "घरात पाणी शिरले आहे, कुटुंब छतावर अडकले, जीव वाचवा, मदत हवी"
    res_evac = citizen_nlp.analyze_report_text(mr_evac)
    assert res_evac["detected_language"] == "mr"
    assert res_evac["classification"] == "evacuation_needed"
    assert res_evac["urgency_score"] >= 0.90


def test_citizen_nlp_hindi_depth_and_urgency():
    # Hindi waist depth
    hi_text = "अंधेरी सबवे में कमर तक पानी भर गया है, रास्ता बंद"
    res = citizen_nlp.analyze_report_text(hi_text)
    assert res["detected_language"] == "hi"
    assert res["is_flood_related"] is True
    assert res["extracted_depth_m"] == 1.00
    assert "Andheri Subway" in res["extracted_landmarks"]

    # Hindi evacuation
    hi_evac = "पानी बहुत बढ़ गया है, लोग फंसे हुए हैं, डूब रहे हैं, मदद चाहिए, नाव भेजो"
    res_evac = citizen_nlp.analyze_report_text(hi_evac)
    assert res_evac["detected_language"] == "hi"
    assert res_evac["classification"] == "evacuation_needed"
    assert res_evac["urgency_score"] >= 0.90


def test_citizen_nlp_numeric_measurements():
    # Feet
    res_ft = citizen_nlp.analyze_report_text("Around 3 feet water logged outside station")
    assert res_ft["extracted_depth_m"] == pytest.approx(0.91, 0.05)

    # Meters
    res_m = citizen_nlp.analyze_report_text("Water level is 1.5 meters high on road")
    assert res_m["extracted_depth_m"] == 1.50


# ---------------------------------------------------------------------------
# 2. SocialNLPClassifier Unit Tests
# ---------------------------------------------------------------------------

def test_social_nlp_classifier_multilingual():
    # Empty
    res_empty = nlp_classifier.classify_text("")
    assert res_empty["classification"] == "noise"
    assert res_empty["is_flood_related"] is False

    # English waterlogging with landmark
    res_en = nlp_classifier.classify_text("Heavy rains causing waterlogging at Sion circle, avoid area")
    assert res_en["is_flood_related"] is True
    assert res_en["classification"] == "waterlogging"
    assert "Sion" in res_en["extracted_landmarks"]
    assert res_en["ward_id"] == "BMC-FN"

    # Marathi urgent
    res_mr = nlp_classifier.classify_text("दादर टीटी येथे छातीभर पाणी, वीज पुरवठा खंडित, धोकादायक परिस्थिती")
    assert res_mr["language"] == "mr"
    assert res_mr["classification"] == "urgent"
    assert res_mr["urgency_score"] >= 0.70
    assert "Dadar" in res_mr["extracted_landmarks"]
    assert res_mr["ward_id"] == "BMC-GN"

    # Hindi rescue
    res_hi = nlp_classifier.classify_text("कुर्ला कमानी में भारी जलभराव, कई परिवार फंसे हुए हैं, तुरंत नाव भेजो")
    assert res_hi["language"] == "hi"
    assert res_hi["classification"] == "evacuation_needed"
    assert res_hi["urgency_score"] >= 0.90
    assert "Kamani" in res_hi["extracted_landmarks"] or "Kurla" in res_hi["extracted_landmarks"]
    assert res_hi["ward_id"] == "BMC-L"


# ---------------------------------------------------------------------------
# 3. Separation of Depths & Operator Independence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_depth_separation_citizen_cv_nlp():
    """Verify citizen reported depth, CV depth, and NLP depth remain strictly isolated."""
    async with async_session_factory() as db:
        rep_id = f"test-depth-sep-{uuid.uuid4().hex[:8]}"
        # Citizen reported depth is 'ankle', but description mentions 'waist deep', and CV is null
        desc = "Water is waist deep near Gandhi Market"
        nlp_out = citizen_nlp.analyze_report_text(desc)
        assert nlp_out["extracted_depth_m"] == 1.00  # NLP extracted depth

        report = CitizenReport(
            report_id=rep_id,
            ward_id="BMC-FN",
            location=func.ST_SetSRID(func.ST_Point(72.8600, 19.0300), 4326),
            water_depth="ankle",  # Citizen reported depth
            image_url=None,
            cv_verified=False,
            cv_water_depth_m=None,  # CV depth
            cv_confidence=None,
            description=desc,
            is_duplicate=False,
            operator_verification_status="pending",
            submitted_at=datetime.now(timezone.utc),
        )
        db.add(report)

        nlp_row = CitizenReportNLPAnalysis(
            report_id=rep_id,
            model_version=nlp_out["model_version"],
            classification=nlp_out["classification"],
            confidence=nlp_out["confidence"],
            urgency_score=nlp_out["urgency_score"],
            is_flood_related=nlp_out["is_flood_related"],
            is_waterlogging=nlp_out["is_waterlogging"],
            is_spam=nlp_out["is_spam"],
            detected_language=nlp_out["detected_language"],
            extracted_depth_m=nlp_out["extracted_depth_m"],
            extracted_landmarks=nlp_out["extracted_landmarks"],
            matched_keywords=nlp_out["matched_keywords"],
            provenance=nlp_out["provenance"],
            processed_at=datetime.now(timezone.utc),
        )
        db.add(nlp_row)
        await db.commit()

        # Query back and verify separation
        fetched = (
            await db.execute(
                select(CitizenReport, CitizenReportNLPAnalysis)
                .join(CitizenReportNLPAnalysis, CitizenReportNLPAnalysis.report_id == CitizenReport.report_id)
                .where(CitizenReport.report_id == rep_id)
            )
        ).first()

        assert fetched is not None
        rep, nlp_rec = fetched
        assert rep.water_depth == "ankle"  # Citizen depth preserved!
        assert rep.cv_water_depth_m is None  # CV depth preserved!
        assert nlp_rec.extracted_depth_m == 1.00  # NLP depth separate!
        assert rep.operator_verification_status == "pending"  # NLP does not promote to confirmed!

        # Cleanup isolated test record
        await db.delete(nlp_rec)
        await db.delete(rep)
        await db.commit()


# ---------------------------------------------------------------------------
# 4. Social NLP Derived Artifact Persistence & Reprocessing Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_social_nlp_derived_artifact_processing_and_idempotency():
    """Verify Engine C NLP creates verifiable derived artifacts and supports reprocessing."""
    from backend.models.database import engine
    await engine.dispose()
    async with async_session_factory() as db:
        unique_post_id = f"test-x-{uuid.uuid4().hex[:12]}"
        post = SocialMediaPost(
            platform="x",
            external_post_id=unique_post_id,
            original_url=f"https://x.com/user/status/{unique_post_id}",
            text_content="Water rising rapidly at Milan Subway Santacruz, waist deep water",
            posted_at=datetime.now(timezone.utc),
            collected_at=datetime.now(timezone.utc),
            processing_status="collected",
            source_status="unverified",
            source_provenance={"test": True},
        )
        db.add(post)
        await db.commit()
        await db.refresh(post)

        try:
            # First process run
            res1 = await social_nlp_service.process_post(db, post)
            assert res1["classification"] in ("urgent", "waterlogging")
            assert "Milan Subway" in res1["extracted_landmarks"]
            assert res1["mapped_ward_id"] == "BMC-HW"
            assert post.processing_status == "nlp_processed"
            assert post.ward_id == "BMC-HW"
            assert post.ward_assignment_provenance == "nlp_gazetteer_extracted"

            # Check artifact in DB
            artifact1 = (
                await db.execute(
                    select(SocialPostDerivedArtifact).where(
                        SocialPostDerivedArtifact.social_post_id == post.id,
                        SocialPostDerivedArtifact.artifact_type == "nlp",
                    )
                )
            ).scalar_one_or_none()
            assert artifact1 is not None
            assert artifact1.payload["classification"] == res1["classification"]

            # Reprocess run (idempotency check)
            res2 = await social_nlp_service.process_post(db, post, reprocess=True)
            assert res2["classification"] == res1["classification"]

            # Ensure only 1 artifact row exists
            artifacts_count = (
                await db.scalar(
                    select(func.count(SocialPostDerivedArtifact.id)).where(
                        SocialPostDerivedArtifact.social_post_id == post.id,
                        SocialPostDerivedArtifact.artifact_type == "nlp",
                    )
                )
            )
            assert artifacts_count == 1

        finally:
            # Cleanup test artifacts and post
            await db.execute(
                select(SocialPostDerivedArtifact).where(SocialPostDerivedArtifact.social_post_id == post.id)
            )
            await db.delete(post)
            await db.commit()


# ---------------------------------------------------------------------------
# 5. Report Intelligence Reliability Scoring with NLP
# ---------------------------------------------------------------------------

def test_report_intelligence_reliability_with_and_without_nlp():
    """Verify ReportIntelligenceEngine incorporates NLP without breaking existing calculations."""
    intelligence = ReportIntelligenceEngine(None)  # calculate_report_reliability is synchronous

    # Base report without NLP
    base_rep = {
        "cv_verified": True,
        "cv_confidence": 0.85,
        "is_duplicate": False,
        "description": "Some description",
        "image_url": "/uploads/test.jpg",
        "nlp_analysis": None,
    }
    res_base = intelligence.calculate_report_reliability(base_rep)
    score_base = res_base["reliability_score"]
    assert 0.0 <= score_base <= 1.0

    # With flood-verified NLP
    nlp_verified_rep = {
        **base_rep,
        "nlp_analysis": {
            "nlp_verified": True,
            "is_spam": False,
            "is_flood_related": True,
            "confidence": 0.85,
        },
    }
    res_nlp = intelligence.calculate_report_reliability(nlp_verified_rep)
    score_nlp = res_nlp["reliability_score"]
    assert score_nlp >= score_base

    # With spam NLP (reliability must drop significantly)
    spam_rep = {
        **base_rep,
        "nlp_analysis": {
            "nlp_verified": False,
            "is_spam": True,
            "is_flood_related": False,
            "confidence": 0.95,
        },
    }
    res_spam = intelligence.calculate_report_reliability(spam_rep)
    score_spam = res_spam["reliability_score"]
    assert score_spam < score_base
    assert score_spam == pytest.approx(score_base - 0.50, 0.01)
