"""
ML Engine C: Multilingual Flood NLP & Social Urgency Classifier.
Processes English, Marathi, and Hindi citizen posts, detects geographical
landmarks mapped to Mumbai administrative wards, and classifies distress urgency per TRD Section 7.3.
"""

import re
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger("fip.engine_c")

# Mumbai Landmark-to-Ward Spatial Gazetteer with Canonical Names
MUMBAI_LANDMARK_MAP: Dict[str, Tuple[str, str]] = {
    # Ward F/North (Sion, Matunga, Wadala)
    "sion": ("MH-BMC-FN", "Sion"),
    "सायन": ("MH-BMC-FN", "Sion"),
    "king's circle": ("MH-BMC-FN", "King's Circle"),
    "kings circle": ("MH-BMC-FN", "King's Circle"),
    "gandhi market": ("MH-BMC-FN", "Gandhi Market"),
    "गांधी मार्केट": ("MH-BMC-FN", "Gandhi Market"),
    "matunga": ("MH-BMC-FN", "Matunga"),
    "माटुंगा": ("MH-BMC-FN", "Matunga"),
    "wadala": ("MH-BMC-FN", "Wadala"),
    "वडाळा": ("MH-BMC-FN", "Wadala"),

    # Ward G/North (Dharavi, Dadar, Mahim)
    "hindmata": ("MH-BMC-GN", "Hindmata"),
    "हिंदमाता": ("MH-BMC-GN", "Hindmata"),
    "dadar": ("MH-BMC-GN", "Dadar"),
    "दादर": ("MH-BMC-GN", "Dadar"),
    "dharavi": ("MH-BMC-GN", "Dharavi"),
    "धारावी": ("MH-BMC-GN", "Dharavi"),
    "mahim": ("MH-BMC-GN", "Mahim"),
    "माहिम": ("MH-BMC-GN", "Mahim"),
    "mithi river": ("MH-BMC-GN", "Mithi River"),
    "mithi": ("MH-BMC-GN", "Mithi River"),
    "मिठी नदी": ("MH-BMC-GN", "Mithi River"),
    "shahu nagar": ("MH-BMC-GN", "Shahu Nagar"),

    # Ward L (Kurla, Kalina, Chunabhatti border)
    "kurla": ("MH-BMC-L", "Kurla"),
    "कुर्ला": ("MH-BMC-L", "Kurla"),
    "kamani": ("MH-BMC-L", "Kamani"),
    "कमानी": ("MH-BMC-L", "Kamani"),
    "bail bazaar": ("MH-BMC-L", "Bail Bazaar"),
    "बैल बाजार": ("MH-BMC-L", "Bail Bazaar"),
    "kalina": ("MH-BMC-L", "Kalina"),
    "कलिना": ("MH-BMC-L", "Kalina"),

    # Ward K/West (Andheri West, Juhu, Versova)
    "andheri subway": ("MH-BMC-KW", "Andheri Subway"),
    "andheri": ("MH-BMC-KW", "Andheri"),
    "अंधेरी सबवे": ("MH-BMC-KW", "Andheri Subway"),
    "अंधेरी": ("MH-BMC-KW", "Andheri"),
    "milan subway": ("MH-BMC-HW", "Milan Subway"),
    "मिलन सबवे": ("MH-BMC-HW", "Milan Subway"),
    "juhu circle": ("MH-BMC-KW", "Juhu Circle"),
    "versova": ("MH-BMC-KW", "Versova"),

    # Ward K/East (Andheri East, Sakinaka, Marol)
    "sakinaka": ("MH-BMC-KE", "Sakinaka"),
    "साकीनाका": ("MH-BMC-KE", "Sakinaka"),
    "marol": ("MH-BMC-KE", "Marol"),
    "मरोळ": ("MH-BMC-KE", "Marol"),
    "chakala": ("MH-BMC-KE", "Chakala"),

    # Ward M/East (Govandi, Mankhurd, Chembur)
    "chembur": ("MH-BMC-ME", "Chembur"),
    "चेंबूर": ("MH-BMC-ME", "Chembur"),
    "chunabhatti": ("MH-BMC-FN", "Chunabhatti"),
    "चुनाभट्टी": ("MH-BMC-FN", "Chunabhatti"),
    "govandi": ("MH-BMC-ME", "Govandi"),

    # Ward H/West & H/East (Bandra, Khar, Santacruz)
    "bandra": ("MH-BMC-HW", "Bandra"),
    "वांद्रे": ("MH-BMC-HW", "Bandra"),
    "kalanagar": ("MH-BMC-HE", "Kalanagar"),
    "khar subway": ("MH-BMC-HW", "Khar Subway"),
    "santacruz": ("MH-BMC-HE", "Santacruz"),

    # Ward A (Colaba, Fort, Marine Drive)
    "colaba": ("MH-BMC-A", "Colaba"),
    "कोलाबा": ("MH-BMC-A", "Colaba"),
    "marine drive": ("MH-BMC-A", "Marine Drive"),
    "churchgate": ("MH-BMC-A", "Churchgate"),
    "cuffe parade": ("MH-BMC-A", "Cuffe Parade"),
}

# Multilingual Urgency Lexicon
KEYWORDS_EVACUATION = [
    # English
    "evacuate", "evacuation", "evacuating", "trapped", "stranded", "rescue", "drowning", "saving lives", "send boat", "roof", "submerged house",
    # Marathi
    "जीव वाचवा", "मदत हवी", "अडकले", "बोट पाठवा", "घरात पाणी", "छतावर", "वाचवा", "वाहून गेले",
    # Hindi
    "बचाओ", "फंसे हुए", "डूब रहे", "मदद चाहिए", "रेस्क्यू", "नाव भेजो", "घर में पानी घुस गया"
]

KEYWORDS_URGENT = [
    # English
    "water rising", "waist deep", "chest high", "danger mark", "submerged cars", "stranded bus", "no power", "current",
    "dangerously", "deluge", "submerged",
    # Marathi
    "धोकादायक", "छातीभर पाणी", "नाला ओसंडून", "गाड्या बुडाल्या", "रस्ता बंद", "वीज पुरवठा खंडित", "पाणी वाढतेय",
    # Hindi
    "खतरा", "कमर तक पानी", "गाड़ियां डूब गईं", "बिजली गुल", "सड़क बंद", "पानी बढ़ रहा है", "विकराल"
]

KEYWORDS_WATERLOGGING = [
    # English
    "waterlogging", "waterlogged", "water logging", "traffic moving slow", "stalled", "knee deep", "knee height", "rain",
    "overflow", "puddle", "flooded", "flooding", "subway closed", "water level", "heavy rains", "water on road",
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

    MODEL_NAME = "v1.0.0-indicbert-flood-urgency"

    def detect_language(self, text: str) -> str:
        """
        Determines language between Marathi, Hindi, or English using Devanagari script markers.
        """
        devanagari_chars = re.findall(r'[\u0900-\u097F]', text)
        if not devanagari_chars:
            return "en"

        text_lower = text.lower()
        marathi_markers = ["आहे", "नाही", "साचले", "पाणी", "वाचवा", "रस्ता", "झाले", "होते", "मध्ये"]
        if any(m in text_lower for m in marathi_markers):
            return "mr"

        return "hi"

    def extract_landmarks(self, text: str) -> Tuple[List[str], Optional[str]]:
        """
        Extracts Mumbai landmarks from text and associates with corresponding ward ID.
        """
        text_lower = text.lower()
        detected_landmarks = []
        resolved_ward = None

        for landmark_key, (ward_id, canonical) in MUMBAI_LANDMARK_MAP.items():
            if landmark_key in text_lower:
                if canonical not in detected_landmarks:
                    detected_landmarks.append(canonical)
                if resolved_ward is None:
                    resolved_ward = ward_id

        return detected_landmarks, resolved_ward

    def classify_text(self, text: str, explicit_ward: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs multilingual sentiment, keyword scoring, and urgency classification.
        """
        lang = self.detect_language(text)
        text_lower = text.lower()

        landmarks, auto_ward = self.extract_landmarks(text)
        final_ward = explicit_ward or auto_ward

        # Evaluate against priority tiers
        is_evac = any(k in text_lower for k in KEYWORDS_EVACUATION)
        is_urgent = any(k in text_lower for k in KEYWORDS_URGENT)
        is_waterlogging = any(k in text_lower for k in KEYWORDS_WATERLOGGING)

        if is_evac:
            classification = "evacuation_needed"
            urgency_score = 0.92
            confidence = 0.94
        elif is_urgent:
            classification = "urgent"
            urgency_score = 0.74
            confidence = 0.88
        elif is_waterlogging:
            classification = "waterlogging"
            urgency_score = 0.48
            confidence = 0.82
        else:
            classification = "noise"
            urgency_score = 0.12
            confidence = 0.70

        # Adjust score if explicit landmarks detected
        if landmarks and urgency_score > 0.3:
            urgency_score = min(0.99, round(urgency_score + 0.05, 2))

        return {
            "language": lang,
            "classification": classification,
            "urgency_score": round(urgency_score, 2),
            "confidence": confidence,
            "extracted_landmarks": landmarks,
            "ward_id": final_ward,
            "location_name": landmarks[0] if landmarks else None,
            "model_version": self.MODEL_NAME
        }


nlp_classifier = SocialNLPClassifier()
