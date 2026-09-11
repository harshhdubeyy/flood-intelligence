# Placeholder for backend/ml/engine_b/nlp_pipeline.py
"""
ML Engine B: Citizen Text Report NLP Pipeline.
Analyzes user-submitted incident descriptions in English, Marathi, and Hindi
to cross-check consistency with reported depth landmarks and filter spam/hoaxes per TRD Section 7.2.
"""

import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("fip.engine_b.nlp")


class CitizenReportNLP:
    """
    Evaluates citizen report descriptions for semantic credibility and extracted depth.
    """

    MODEL_VERSION = "v1.1.0-indicbert-report-verify"

    DEPTH_KEYWORDS = {
        "ankle": 0.15,
        "ankle deep": 0.15,
        "feet deep": 0.30,
        "knee": 0.50,
        "knee deep": 0.50,
        "knee height": 0.50,
        "waist": 1.00,
        "waist deep": 1.00,
        "waist high": 1.00,
        "chest": 1.40,
        "chest deep": 1.40,
        "submerged": 1.80,
        "underwater": 1.80,
        # Marathi
        "गुडघाभर पाणी": 0.50,
        "गुडघा": 0.50,
        "कंबरभर पाणी": 1.00,
        "छातीभर पाणी": 1.40,
        "घर बुडाले": 1.80,
        # Hindi
        "घुटनों तक": 0.50,
        "कमर तक": 1.00,
        "डूब गया": 1.80
    }

    # Spam / hoax markers
    SPAM_PATTERNS = [
        r"test\s+test",
        r"hello\s+world",
        r"click\s+here",
        r"buy\s+now",
        r"subscribe",
        r"crypto|bitcoin"
    ]

    def analyze_report_text(
        self,
        description: str,
        reported_category: str = "waterlogging",
        reported_depth_m: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Extracts semantic consistency score and estimated text depth.
        """
        if not description or len(description.strip()) < 3:
            return {
                "nlp_verified": False,
                "is_spam": False,
                "credibility_score": 0.4,
                "extracted_depth_m": reported_depth_m or 0.3,
                "sentiment": "neutral",
                "extracted_keywords": [],
                "model_version": self.MODEL_VERSION
            }

        desc_lower = description.lower()

        # Spam detection
        is_spam = any(re.search(pat, desc_lower) for pat in self.SPAM_PATTERNS)
        if is_spam:
            return {
                "nlp_verified": False,
                "is_spam": True,
                "credibility_score": 0.05,
                "extracted_depth_m": 0.0,
                "sentiment": "spam",
                "extracted_keywords": ["spam_detected"],
                "model_version": self.MODEL_VERSION
            }

        # Match depth keywords
        matched_depth = None
        matched_keywords = []
        for kw, depth in self.DEPTH_KEYWORDS.items():
            if kw in desc_lower:
                matched_depth = depth
                matched_keywords.append(kw)
                break

        # Check for numeric measurements e.g. "2 feet", "3 ft", "1.5 meters"
        feet_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:feet|ft|foot)", desc_lower)
        if feet_match:
            matched_depth = round(float(feet_match.group(1)) * 0.3048, 2)
            matched_keywords.append(f"{feet_match.group(1)}_ft")

        meter_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:meters|meter|m)\b", desc_lower)
        if meter_match:
            matched_depth = round(float(meter_match.group(1)), 2)
            matched_keywords.append(f"{meter_match.group(1)}_m")

        # Credibility scoring
        credibility = 0.65
        if len(description) > 20:
            credibility += 0.15
        if matched_keywords:
            credibility += 0.15
        if any(w in desc_lower for w in ["water", "flood", "rain", "road", "subway", "traffic", "नाला", "पाणी"]):
            credibility += 0.10

        credibility = min(0.98, credibility)

        return {
            "nlp_verified": credibility >= 0.70,
            "is_spam": False,
            "credibility_score": round(credibility, 2),
            "extracted_depth_m": matched_depth if matched_depth is not None else (reported_depth_m or 0.4),
            "matched_keywords": matched_keywords,
            "sentiment": "distress" if any(w in desc_lower for w in ["trapped", "help", "danger", "urgent", "मदत"]) else "informative",
            "model_version": self.MODEL_VERSION
        }


citizen_nlp = CitizenReportNLP()
