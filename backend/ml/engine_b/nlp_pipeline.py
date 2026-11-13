"""
ML Engine B: Multilingual Citizen Text Report NLP Pipeline.
Analyzes user-submitted incident descriptions in English, Marathi, and Hindi
to detect flood relevance, waterlogging, water depth mentions, urgency indicators,
spam/hoaxes, and extracted localities per TRD Section 7.2.

Note on AI provenance: This pipeline uses a calibrated multilingual gazetteer,
morphological Devanagari markers, and heuristic depth parsing (heuristic-indic-lexical-v1).
It does not claim deep transformer-based inference (IndicBERT) since fine-tuned
transformer model weights are not packaged in this deployment.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.ml.engine_c.nlp_classifier import MUMBAI_LANDMARK_MAP

logger = logging.getLogger("fip.engine_b.nlp")


class CitizenReportNLP:
    """
    Evaluates citizen report descriptions for semantic consistency, extracted depth,
    urgency classification, and spam detection across English, Marathi, and Hindi.
    """

    MODEL_VERSION = "heuristic-indic-lexical-v1"

    DEPTH_KEYWORDS: Dict[str, float] = {
        # English categorical / landmarks
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
        "chest high": 1.40,
        "submerged": 1.80,
        "underwater": 1.80,
        # Marathi
        "घोटाभर पाणी": 0.15,
        "घोटाभर": 0.15,
        "पावलांएवढे": 0.15,
        "गुडघाभर पाणी": 0.50,
        "गुडघाभर": 0.50,
        "गुडघ्यापर्यंत": 0.50,
        "गुडघा": 0.50,
        "कंबरभर पाणी": 1.00,
        "कंबरभर": 1.00,
        "कमरेपर्यंत": 1.00,
        "छातीभर पाणी": 1.40,
        "छातीभर": 1.40,
        "छातीपर्यंत": 1.40,
        "घर बुडाले": 1.80,
        "पाण्याखाली": 1.80,
        "बुडाले": 1.80,
        # Hindi
        "टखनों तक": 0.15,
        "टखने भर": 0.15,
        "घुटनों तक": 0.50,
        "घुटने भर": 0.50,
        "घुटनों भर": 0.50,
        "कमर तक": 1.00,
        "कमर भर": 1.00,
        "कमर बराबर": 1.00,
        "छाती तक": 1.40,
        "छाती भर": 1.40,
        "डूब गया": 1.80,
        "डूब गए": 1.80,
        "पानी में डूबा": 1.80,
        "जलमग्न": 1.80,
    }

    FLOOD_KEYWORDS: List[str] = [
        # English
        "waterlogging", "waterlogged", "water logging", "flood", "flooding", "flooded",
        "rain", "rainfall", "heavy rain", "overflow", "overflowing", "subway closed",
        "stalled", "water level", "traffic jam", "deluge", "drainage", "nullah", "nala",
        # Marathi
        "पाणी साचले", "साचलेले पाणी", "पाणी भरले", "पाणी शिरले", "पूर", "मुसळधार पाऊस",
        "मुसळधार", "नाला ओसंडून", "रस्ता बंद", "वाहतूक ठप्प", "तुंबले",
        # Hindi
        "जलभराव", "पानी भरा", "पानी भर गया", "बाढ़", "भारी बारिश", "नाला", "सड़क बंद", "जाम",
    ]

    URGENCY_EVACUATION: List[str] = [
        "evacuate", "evacuation", "trapped", "stranded", "rescue", "drowning", "saving lives",
        "send boat", "roof", "submerged house", "dangerously high",
        "जीव वाचवा", "मदत हवी", "अडकले", "बोट पाठवा", "घरात पाणी शिरले", "छतावर", "वाचवा",
        "बचाओ", "फंसे हुए", "डूब रहे", "मदद चाहिए", "रेस्क्यू", "नाव भेजो", "घर में पानी घुस गया",
    ]

    URGENCY_HIGH: List[str] = [
        "water rising", "waist deep", "chest high", "danger mark", "submerged cars",
        "stranded bus", "no power", "current", "deluge", "overflowing nala",
        "धोकादायक", "छातीभर पाणी", "गाड्या बुडाल्या", "रस्ता बंद", "पाणी वाढतेय", "वीज पुरवठा खंडित",
        "खतरा", "कमर तक पानी", "गाड़ियां डूब गईं", "बिजली गुल", "पानी बढ़ रहा है", "विकराल",
    ]

    SPAM_PATTERNS: List[str] = [
        r"test\s+test",
        r"hello\s+world",
        r"click\s+here",
        r"buy\s+now",
        r"subscribe",
        r"crypto|bitcoin",
        r"free\s+cash",
        r"cheap\s+loans",
        r"casino|poker",
        r"discount\s+code",
    ]

    def detect_language(self, text: str) -> str:
        """Determines language between English ('en'), Marathi ('mr'), or Hindi ('hi')."""
        devanagari_chars = re.findall(r"[\u0900-\u097F]", text)
        if not devanagari_chars:
            return "en"

        text_lower = text.lower()
        marathi_markers = [
            "आहे", "नाही", "साचले", "पाणी", "वाचवा", "रस्ता", "झाले", "होते",
            "मध्ये", "तुंबले", "भरले", "येथे", "विभागात", "सखल",
        ]
        if any(m in text_lower for m in marathi_markers):
            return "mr"

        return "hi"

    def extract_landmarks(self, text: str) -> Tuple[List[str], Optional[str]]:
        """Extracts Mumbai canonical localities and maps to ward ID when present."""
        text_lower = text.lower()
        detected: List[str] = []
        resolved_ward: Optional[str] = None

        for landmark_key, (ward_id, canonical) in MUMBAI_LANDMARK_MAP.items():
            pattern = rf"(?<!\w){re.escape(landmark_key)}(?!\w)"
            if re.search(pattern, text_lower):
                if canonical not in detected:
                    detected.append(canonical)
                if resolved_ward is None:
                    resolved_ward = ward_id

        return detected, resolved_ward

    def analyze_report_text(
        self,
        description: Optional[str],
        reported_category: str = "waterlogging",
        reported_depth_m: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Extracts semantic consistency score, estimated text depth, urgency,
        spam classification, and entities from citizen report text.
        """
        now_ts = datetime.now(timezone.utc).isoformat()
        if not description or len(description.strip()) < 3:
            return {
                "nlp_verified": False,
                "is_spam": False,
                "is_flood_related": False,
                "is_waterlogging": False,
                "classification": "noise",
                "urgency_score": 0.10,
                "confidence": 0.40,
                "detected_language": "und" if description else "en",
                "credibility_score": 0.35,
                "extracted_depth_m": None,
                "extracted_landmarks": [],
                "matched_keywords": [],
                "model_version": self.MODEL_VERSION,
                "processed_at": now_ts,
                "provenance": {
                    "method": "heuristic_indic_lexical",
                    "reason": "Description is empty or under 3 characters.",
                    "disclaimer": "Heuristic lexical analysis; not an official confirmation.",
                },
            }

        desc_raw = description.strip()
        desc_lower = desc_raw.lower()
        lang = self.detect_language(desc_raw)

        # 1. Spam detection
        is_spam = any(re.search(pat, desc_lower, re.IGNORECASE) for pat in self.SPAM_PATTERNS)
        if is_spam:
            return {
                "nlp_verified": False,
                "is_spam": True,
                "is_flood_related": False,
                "is_waterlogging": False,
                "classification": "spam",
                "urgency_score": 0.0,
                "confidence": 0.95,
                "detected_language": lang,
                "credibility_score": 0.05,
                "extracted_depth_m": None,
                "extracted_landmarks": [],
                "matched_keywords": ["spam_pattern_detected"],
                "model_version": self.MODEL_VERSION,
                "processed_at": now_ts,
                "provenance": {
                    "method": "heuristic_indic_lexical",
                    "reason": "Text matches known spam/promotional markers.",
                    "disclaimer": "Heuristic lexical analysis; not an official confirmation.",
                },
            }

        # 2. Match depth keywords & measurements
        matched_depth: Optional[float] = None
        matched_keywords: List[str] = []

        for kw, depth in self.DEPTH_KEYWORDS.items():
            if kw in desc_lower:
                matched_depth = depth
                matched_keywords.append(kw)
                break

        # Check for numeric measurements: e.g., "2 feet", "3 ft", "1.5 meters", "2 मीटर", "3 फूट"
        feet_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:feet|ft|foot|फूट|फुट)", desc_lower)
        if feet_match:
            try:
                matched_depth = round(float(feet_match.group(1)) * 0.3048, 2)
                matched_keywords.append(f"{feet_match.group(1)}_ft")
            except ValueError:
                pass

        meter_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:meters|meter|m|मीटर)\b", desc_lower)
        if meter_match:
            try:
                matched_depth = round(float(meter_match.group(1)), 2)
                matched_keywords.append(f"{meter_match.group(1)}_m")
            except ValueError:
                pass

        # 3. Flood & Waterlogging detection
        is_flood_related = any(kw in desc_lower for kw in self.FLOOD_KEYWORDS)
        is_waterlogging = any(
            kw in desc_lower
            for kw in [
                "waterlogging", "waterlogged", "water logging", "पाणी साचले",
                "साचलेले पाणी", "तुंबले", "जलभराव", "पानी भरा",
            ]
        ) or (is_flood_related and matched_depth is not None)

        for kw in self.FLOOD_KEYWORDS:
            if kw in desc_lower and kw not in matched_keywords:
                matched_keywords.append(kw)

        # 4. Landmark extraction
        landmarks, landmark_ward = self.extract_landmarks(desc_raw)

        # 5. Urgency evaluation
        is_evacuation = any(kw in desc_lower for kw in self.URGENCY_EVACUATION)
        is_urgent = any(kw in desc_lower for kw in self.URGENCY_HIGH) or (
            matched_depth is not None and matched_depth >= 1.0
        )

        if is_evacuation:
            classification = "evacuation_needed"
            urgency_score = 0.92
            confidence = 0.90
        elif is_urgent:
            classification = "urgent"
            urgency_score = 0.75
            confidence = 0.85
        elif is_waterlogging:
            classification = "waterlogging"
            urgency_score = 0.50
            confidence = 0.80
        elif is_flood_related:
            classification = "general_weather"
            urgency_score = 0.30
            confidence = 0.70
        else:
            classification = "noise"
            urgency_score = 0.10
            confidence = 0.65

        # 6. Semantic credibility score (0.0 to 1.0)
        credibility = 0.50
        if is_flood_related:
            credibility += 0.20
        if matched_depth is not None:
            credibility += 0.15
        if landmarks:
            credibility += 0.10
        if len(desc_raw) > 25:
            credibility += 0.05

        credibility = round(max(0.10, min(0.98, credibility)), 2)
        nlp_verified = credibility >= 0.70 and is_flood_related

        return {
            "nlp_verified": nlp_verified,
            "is_spam": False,
            "is_flood_related": is_flood_related,
            "is_waterlogging": is_waterlogging,
            "classification": classification,
            "urgency_score": round(urgency_score, 2),
            "confidence": round(confidence, 2),
            "detected_language": lang,
            "credibility_score": credibility,
            "extracted_depth_m": matched_depth,
            "extracted_landmarks": landmarks,
            "matched_keywords": matched_keywords[:10],
            "model_version": self.MODEL_VERSION,
            "processed_at": now_ts,
            "provenance": {
                "method": "heuristic_indic_lexical",
                "extracted_ward_id": landmark_ward,
                "disclaimer": "Heuristic lexical analysis; not an official confirmation.",
            },
        }


citizen_nlp = CitizenReportNLP()
