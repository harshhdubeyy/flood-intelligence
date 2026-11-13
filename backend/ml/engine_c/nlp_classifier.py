"""
ML Engine C: Multilingual Flood NLP & Social Urgency Classifier.
Processes English, Marathi, and Hindi citizen posts and public social records,
detects geographical landmarks mapped to Mumbai administrative wards, and
classifies distress urgency per TRD Section 7.3.

Note on AI provenance: This pipeline uses a calibrated multilingual gazetteer,
morphological Devanagari markers, and heuristic urgency weighting (heuristic-indic-urgency-v1).
It does not claim deep transformer-based inference (IndicBERT) since fine-tuned
transformer model weights are not packaged in this deployment.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("fip.engine_c")

# Mumbai Landmark-to-Ward Spatial Gazetteer with Canonical Names
MUMBAI_LANDMARK_MAP: Dict[str, Tuple[str, str]] = {
    # Ward F/North (Sion, Matunga, Wadala)
    "sion": ("BMC-FN", "Sion"),
    "सायन": ("BMC-FN", "Sion"),
    "king's circle": ("BMC-FN", "King's Circle"),
    "kings circle": ("BMC-FN", "King's Circle"),
    "gandhi market": ("BMC-FN", "Gandhi Market"),
    "गांधी मार्केट": ("BMC-FN", "Gandhi Market"),
    "matunga": ("BMC-FN", "Matunga"),
    "माटुंगा": ("BMC-FN", "Matunga"),
    "wadala": ("BMC-FN", "Wadala"),
    "वडाळा": ("BMC-FN", "Wadala"),

    # Ward G/North (Dharavi, Dadar, Mahim)
    "hindmata": ("BMC-GN", "Hindmata"),
    "हिंदमाता": ("BMC-GN", "Hindmata"),
    "dadar": ("BMC-GN", "Dadar"),
    "दादर": ("BMC-GN", "Dadar"),
    "dharavi": ("BMC-GN", "Dharavi"),
    "धारावी": ("BMC-GN", "Dharavi"),
    "mahim": ("BMC-GN", "Mahim"),
    "माहिम": ("BMC-GN", "Mahim"),
    "mithi river": ("BMC-GN", "Mithi River"),
    "mithi": ("BMC-GN", "Mithi River"),
    "मिठी नदी": ("BMC-GN", "Mithi River"),
    "shahu nagar": ("BMC-GN", "Shahu Nagar"),

    # Ward L (Kurla, Kalina, Chunabhatti border)
    "kurla": ("BMC-L", "Kurla"),
    "कुर्ला": ("BMC-L", "Kurla"),
    "kamani": ("BMC-L", "Kamani"),
    "कमानी": ("BMC-L", "Kamani"),
    "bail bazaar": ("BMC-L", "Bail Bazaar"),
    "बैल बाजार": ("BMC-L", "Bail Bazaar"),
    "kalina": ("BMC-L", "Kalina"),
    "कलिना": ("BMC-L", "Kalina"),

    # Ward K/West (Andheri West, Juhu, Versova)
    "andheri subway": ("BMC-KW", "Andheri Subway"),
    "andheri": ("BMC-KW", "Andheri"),
    "अंधेरी सबवे": ("BMC-KW", "Andheri Subway"),
    "अंधेरी": ("BMC-KW", "Andheri"),
    "milan subway": ("BMC-HW", "Milan Subway"),
    "मिलन सबवे": ("BMC-HW", "Milan Subway"),
    "juhu circle": ("BMC-KW", "Juhu Circle"),
    "versova": ("BMC-KW", "Versova"),

    # Ward K/East (Andheri East, Sakinaka, Marol)
    "sakinaka": ("BMC-KE", "Sakinaka"),
    "साकीनाका": ("BMC-KE", "Sakinaka"),
    "marol": ("BMC-KE", "Marol"),
    "मरोळ": ("BMC-KE", "Marol"),
    "chakala": ("BMC-KE", "Chakala"),

    # Ward M/East (Govandi, Mankhurd, Chembur)
    "chembur": ("BMC-MW", "Chembur"),
    "चेंबूर": ("BMC-MW", "Chembur"),
    "chunabhatti": ("BMC-FN", "Chunabhatti"),
    "चुनाभट्टी": ("BMC-FN", "Chunabhatti"),
    "govandi": ("BMC-ME", "Govandi"),

    # Ward H/West & H/East (Bandra, Khar, Santacruz)
    "bandra": ("BMC-HW", "Bandra"),
    "वांद्रे": ("BMC-HW", "Bandra"),
    "kalanagar": ("BMC-HE", "Kalanagar"),
    "khar subway": ("BMC-HW", "Khar Subway"),
    "santacruz": ("BMC-HE", "Santacruz"),

    # Ward A (Colaba, Fort, Marine Drive)
    "colaba": ("BMC-A", "Colaba"),
    "कोलाबा": ("BMC-A", "Colaba"),
    "marine drive": ("BMC-A", "Marine Drive"),
    "churchgate": ("BMC-A", "Churchgate"),
    "cuffe parade": ("BMC-A", "Cuffe Parade"),
}

# Multilingual Urgency Lexicon
KEYWORDS_EVACUATION = [
    # English
    "evacuate", "evacuation", "evacuating", "trapped", "stranded", "rescue", "drowning",
    "saving lives", "send boat", "roof", "submerged house",
    # Marathi
    "जीव वाचवा", "मदत हवी", "अडकले", "बोट पाठवा", "घरात पाणी", "छतावर", "वाचवा", "वाहून गेले",
    # Hindi
    "बचाओ", "फंसे हुए", "डूब रहे", "मदद चाहिए", "रेस्क्यू", "नाव भेजो", "घर में पानी घुस गया"
]

KEYWORDS_URGENT = [
    # English
    "water rising", "waist deep", "chest high", "danger mark", "submerged cars", "stranded bus",
    "no power", "current", "dangerously", "deluge", "submerged",
    # Marathi
    "धोकादायक", "छातीभर पाणी", "नाला ओसंडून", "गाड्या बुडाल्या", "रस्ता बंद", "वीज पुरवठा खंडित", "पाणी वाढतेय",
    # Hindi
    "खतरा", "कमर तक पानी", "गाड़ियां डूब गईं", "बिजली गुल", "सड़क बंद", "पानी बढ़ रहा है", "विकराल"
]

KEYWORDS_WATERLOGGING = [
    # English
    "waterlogging", "waterlogged", "water logging", "traffic moving slow", "stalled", "knee deep",
    "knee height", "rain", "overflow", "puddle", "flooded", "flooding", "subway closed",
    "water level", "heavy rains", "water on road",
    # Marathi
    "पाणी साचले", "साचलेले पाणी", "पाणी भरले", "वाहतूक धिम्या गतीने", "गुडघाभर पाणी", "मुसळधार", "पाणी शिरले", "पाऊस",
    # Hindi
    "जलभराव", "पानी भरा", "जाम", "घुटनों तक पानी", "बारिश", "पानी भर गया"
]


class SocialNLPClassifier:
    """
    NLP Classifier and Named Entity Recognizer for social signals (Engine C).
    Detects language, extracts locations, evaluates classification, and produces calibrated urgency scores.
    """

    MODEL_NAME = "heuristic-indic-urgency-v1"

    def detect_language(self, text: str) -> str:
        """Determines language between Marathi ('mr'), Hindi ('hi'), or English ('en')."""
        devanagari_chars = re.findall(r"[\u0900-\u097F]", text)
        if not devanagari_chars:
            return "en"

        text_lower = text.lower()
        marathi_markers = [
            "आहे", "नाही", "साचले", "पाणी", "वाचवा", "रस्ता", "झाले", "होते",
            "मध्ये", "तुंबले", "भरले", "येथे", "विभागात",
        ]
        if any(m in text_lower for m in marathi_markers):
            return "mr"

        return "hi"

    def extract_landmarks(self, text: str) -> Tuple[List[str], Optional[str]]:
        """Extracts Mumbai landmarks from text and associates with corresponding ward ID."""
        text_lower = text.lower()
        detected_landmarks: List[str] = []
        resolved_ward: Optional[str] = None

        for landmark_key, (ward_id, canonical) in MUMBAI_LANDMARK_MAP.items():
            pattern = rf"(?<!\w){re.escape(landmark_key)}(?!\w)"
            if re.search(pattern, text_lower):
                if canonical not in detected_landmarks:
                    detected_landmarks.append(canonical)
                if resolved_ward is None:
                    resolved_ward = ward_id

        return detected_landmarks, resolved_ward

    def classify_text(self, text: Optional[str], explicit_ward: Optional[str] = None) -> Dict[str, Any]:
        """Runs multilingual sentiment, keyword scoring, landmark extraction, and urgency classification."""
        now_ts = datetime.now(timezone.utc).isoformat()
        if not text or len(text.strip()) < 3:
            return {
                "language": "und" if text else "en",
                "classification": "noise",
                "urgency_score": 0.10,
                "confidence": 0.40,
                "is_flood_related": False,
                "is_waterlogging": False,
                "extracted_landmarks": [],
                "ward_id": explicit_ward,
                "location_name": None,
                "model_version": self.MODEL_NAME,
                "processed_at": now_ts,
                "explanation": "Text content is empty or too short for classification.",
                "provenance": {
                    "method": "heuristic_indic_urgency",
                    "disclaimer": "Heuristic lexical analysis; not an official confirmation.",
                },
            }

        text_raw = text.strip()
        text_lower = text_raw.lower()
        lang = self.detect_language(text_raw)

        landmarks, auto_ward = self.extract_landmarks(text_raw)
        final_ward = explicit_ward or auto_ward

        # Evaluate against priority tiers
        is_evac = any(k in text_lower for k in KEYWORDS_EVACUATION)
        is_urgent = any(k in text_lower for k in KEYWORDS_URGENT)
        is_waterlogging = any(k in text_lower for k in KEYWORDS_WATERLOGGING)

        if is_evac:
            classification = "evacuation_needed"
            urgency_score = 0.92
            confidence = 0.90
            explanation = "Urgent distress or rescue request detected."
        elif is_urgent:
            classification = "urgent"
            urgency_score = 0.74
            confidence = 0.85
            explanation = "Rising water, road closures, or hazardous inundation reported."
        elif is_waterlogging:
            classification = "waterlogging"
            urgency_score = 0.48
            confidence = 0.80
            explanation = "Traffic slowdown or waterlogging condition reported."
        else:
            classification = "noise"
            urgency_score = 0.12
            confidence = 0.70
            explanation = "No explicit flood or waterlogging indicators found."

        # Boost urgency slightly if explicit Mumbai landmarks are verified
        if landmarks and urgency_score > 0.3:
            urgency_score = min(0.99, round(urgency_score + 0.05, 2))

        is_flood_related = classification in ("evacuation_needed", "urgent", "waterlogging")

        return {
            "language": lang,
            "classification": classification,
            "urgency_score": round(urgency_score, 2),
            "confidence": round(confidence, 2),
            "is_flood_related": is_flood_related,
            "is_waterlogging": is_waterlogging,
            "extracted_landmarks": landmarks,
            "ward_id": final_ward,
            "location_name": landmarks[0] if landmarks else None,
            "model_version": self.MODEL_NAME,
            "processed_at": now_ts,
            "explanation": explanation,
            "provenance": {
                "method": "heuristic_indic_urgency",
                "extracted_ward_id": auto_ward,
                "disclaimer": "Heuristic lexical analysis; not an official confirmation.",
            },
        }


nlp_classifier = SocialNLPClassifier()
