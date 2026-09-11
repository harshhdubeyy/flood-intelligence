"""
ML Engine B: Multi-Modal Cross-Verification Engine.
Synthesizes Computer Vision image segmentation, text NLP sentiment/depth extraction,
and proximity to BMC weather station telemetry to verify citizen incident reports per TRD Section 7.2.
"""

import logging
from typing import Dict, Any, Optional

from backend.ml.engine_b.cv_water_depth import FloodVisionVerifier, DEPTH_MAPPING
from backend.ml.engine_b.yolo_verify import yolo_verifier
from backend.ml.engine_b.nlp_pipeline import citizen_nlp

logger = logging.getLogger("fip.engine_b.cross_verify")


class MultiModalCrossVerifier:
    """
    Fuses multiple independent signals:
    1. Vision Score (YOLOv8 instance segmentation of water / submerged objects)
    2. Text Score (NLP semantics, depth keyword extraction, spam filtering)
    3. Hydrological Plausibility (Current Ward rain gauge & tide stage)
    """

    VISION_WEIGHT = 0.50
    TEXT_WEIGHT = 0.25
    MET_PLAUSIBILITY_WEIGHT = 0.25

    def __init__(self):
        self.vision_verifier = FloodVisionVerifier()

    def cross_verify(
        self,
        image_bytes: Optional[bytes],
        description: str,
        reported_category: str = "waterlogging",
        reported_water_level: str = "knee",
        ward_rainfall_1h_mm: float = 20.0,
        current_tide_m: float = 3.5
    ) -> Dict[str, Any]:
        """
        Calculates unified authenticity verification score [0.0, 1.0].
        """
        # 1. Text NLP Analysis
        nlp_res = citizen_nlp.analyze_report_text(
            description=description,
            reported_category=reported_category
        )
        if nlp_res.get("is_spam", False):
            return {
                "verified": False,
                "confidence_score": 0.05,
                "rejection_reason": "Spam / irrelevant text detected.",
                "verified_depth_m": 0.0,
                "vision_score": 0.0,
                "nlp_score": 0.05,
                "met_plausibility_score": 0.0
            }

        nlp_score = nlp_res["credibility_score"]

        # 2. Vision Verification
        if image_bytes and len(image_bytes) > 0:
            yolo_res = yolo_verifier.detect_flood_features(image_bytes, reported_category)
            cv_res = self.vision_verifier.analyze_image_bytes(image_bytes, reported_water_level)
            vision_score = max(yolo_res["confidence"], cv_res["cv_confidence"])
            cv_depth = cv_res["cv_water_depth_m"]
        else:
            # Without image, visual evidence is absent
            vision_score = 0.45
            cv_depth = DEPTH_MAPPING.get(reported_water_level.lower(), 0.3)

        # 3. Meteorological Plausibility Score
        # If rainfall > 20 mm/h or tide > 3.8m, flooding in Mumbai is hydrologically very plausible
        met_score = 0.50
        if ward_rainfall_1h_mm > 35.0 or current_tide_m > 4.2:
            met_score = 0.95
        elif ward_rainfall_1h_mm > 15.0 or current_tide_m > 3.5:
            met_score = 0.80
        elif ward_rainfall_1h_mm > 5.0:
            met_score = 0.65
        else:
            met_score = 0.40

        # Composite verification score
        composite_confidence = round(
            (vision_score * self.VISION_WEIGHT) +
            (nlp_score * self.TEXT_WEIGHT) +
            (met_score * self.MET_PLAUSIBILITY_WEIGHT),
            2
        )

        # Verification threshold: 0.65
        is_verified = composite_confidence >= 0.65

        # Unified depth consensus
        raw_candidates = [
            cv_depth,
            nlp_res.get("extracted_depth_m"),
            DEPTH_MAPPING.get(reported_water_level.lower())
        ]
        valid_candidates = [d for d in raw_candidates if d is not None and isinstance(d, (int, float))]
        if valid_candidates:
            verified_depth = round(sum(valid_candidates) / len(valid_candidates), 2)
        else:
            verified_depth = DEPTH_MAPPING.get(reported_water_level.lower(), 0.3)

        return {
            "verified": is_verified,
            "confidence_score": composite_confidence,
            "verified_depth_m": verified_depth,
            "vision_score": vision_score,
            "nlp_score": nlp_score,
            "met_plausibility_score": met_score,
            "extracted_depth_m": verified_depth,
            "details": {
                "nlp": nlp_res,
                "has_photo_evidence": bool(image_bytes and len(image_bytes) > 0)
            }
        }


cross_verifier = MultiModalCrossVerifier()
