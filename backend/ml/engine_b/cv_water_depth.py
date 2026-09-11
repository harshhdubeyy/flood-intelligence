"""
ML Engine B: Computer Vision Water Level & Flood Verification Pipeline.
Processes uploaded flood photographs to detect water presence, identify
submerged reference landmarks, and verify crowdsourced reports per TRD Section 7.2.

Integrates directly with the real Ultralytics YOLO inference pipeline (`yolo_verify.py`).
"""

import logging
from typing import Dict, Any, List, Optional
from io import BytesIO

try:
    from PIL import Image
except ImportError:
    Image = None

from backend.ml.engine_b.yolo_verify import yolo_verifier

logger = logging.getLogger("fip.engine_b.cv")

# Reference mapping for reported categorical heights
DEPTH_MAPPING = {
    "ankle": 0.15,
    "knee": 0.50,
    "waist": 1.00,
    "submerged": 1.80,
}


class FloodVisionVerifier:
    """
    Computer Vision analyzer for ground-truth flood photos.
    Evaluates:
    1. Image validity and integrity (resolution / format check)
    2. Deep learning object detection via Ultralytics YOLO
    3. Water presence verification & confidence
    4. Conservative water depth assessment (distinguishing reported vs CV estimated)
    """

    def __init__(self):
        self.yolo = yolo_verifier

    @property
    def model_version(self) -> str:
        return self.yolo.model_version

    @property
    def model_source(self) -> str:
        return self.yolo.model_source

    def analyze_image_bytes(
        self,
        image_bytes: bytes,
        reported_depth: str = "knee"
    ) -> Dict[str, Any]:
        """
        Executes real YOLO visual verification.
        Combines deep learning model inference with user-reported metadata.
        """
        try:
            # 1. Image sanity and validation check
            if not image_bytes or len(image_bytes) < 100:
                return {
                    "cv_verified": False,
                    "water_detected": False,
                    "cv_water_depth_m": None,
                    "cv_confidence": 0.0,
                    "detected_landmarks": [],
                    "detected_objects": [],
                    "model_version": self.model_version,
                    "model_source": self.model_source,
                    "reported_water_depth": reported_depth,
                    "cv_estimated_depth_category": None,
                    "reason": "Empty or incomplete image payload."
                }

            # 2. Invoke real Ultralytics YOLO inference
            yolo_result = self.yolo.detect_flood_features(
                image_bytes=image_bytes,
                reported_category="waterlogging"
            )

            # Check if image was flagged as invalid/corrupted
            if not yolo_result.get("is_valid_image", True):
                return {
                    "cv_verified": False,
                    "water_detected": False,
                    "cv_water_depth_m": None,
                    "cv_confidence": 0.0,
                    "detected_landmarks": [],
                    "detected_objects": [],
                    "model_version": self.model_version,
                    "model_source": self.model_source,
                    "reported_water_depth": reported_depth,
                    "cv_estimated_depth_category": None,
                    "reason": yolo_result.get("error", "Image rejected during validation.")
                }

            # 3. Extract real inference outcomes
            flood_detected = bool(yolo_result.get("flood_detected", False))
            confidence = float(yolo_result.get("confidence", 0.0))
            detected_objects = yolo_result.get("detected_objects", [])
            detected_landmarks = [obj["class"] for obj in detected_objects]
            model_source = yolo_result.get("model_source", self.model_source)
            model_version = yolo_result.get("model_version", self.model_version)

            # 4. Conservative Water Depth Assessment
            # DO NOT claim YOLO bounding boxes automatically provide metric water depth.
            # Distinguish reported depth from model depth.
            cv_estimated_depth_m = yolo_result.get("estimated_depth_m")
            cv_estimated_depth_cat = yolo_result.get("cv_estimated_depth_category")

            # Verification threshold: confidence >= 0.50 with active flood detection
            cv_verified = flood_detected and confidence >= 0.50

            reason = yolo_result.get("advisory", "")
            if not reason:
                if cv_verified:
                    reason = f"Verified by {model_source} with {len(detected_objects)} detected objects."
                else:
                    reason = f"Unverified: insufficient visual flood indicators detected by {model_source}."

            return {
                "cv_verified": cv_verified,
                "water_detected": flood_detected,
                "cv_water_depth_m": cv_estimated_depth_m,
                "cv_confidence": confidence,
                "detected_landmarks": detected_landmarks,
                "detected_objects": detected_objects,
                "reported_water_depth": reported_depth,
                "cv_estimated_depth_category": cv_estimated_depth_cat,
                "model_version": model_version,
                "model_source": model_source,
                "inference_time_ms": yolo_result.get("inference_time_ms"),
                "reason": reason
            }

        except Exception as exc:
            logger.error(f"Image analysis failed with exception: {exc}")
            return {
                "cv_verified": False,
                "water_detected": False,
                "cv_water_depth_m": None,
                "cv_confidence": 0.0,
                "detected_landmarks": [],
                "detected_objects": [],
                "model_version": self.model_version,
                "model_source": self.model_source,
                "reported_water_depth": reported_depth,
                "cv_estimated_depth_category": None,
                "reason": f"Analysis error: {str(exc)}"
            }


cv_verifier = FloodVisionVerifier()
