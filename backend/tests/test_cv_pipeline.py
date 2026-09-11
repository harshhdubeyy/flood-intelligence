"""
Unit and Integration Tests for ML Engine B: Computer Vision YOLO Pipeline.

Verifies:
1. Valid image inference
2. Corrupted / invalid image handling
3. Sub-minimum resolution image rejection
4. Missing model handling and graceful operating modes
5. Output dictionary structure and field types
6. Separation of reported water depth vs CV-estimated depth
7. Annotation generator utility
"""

try:
    import pytest
except ImportError:
    pytest = None
from io import BytesIO
from typing import Dict, Any

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None

from backend.ml.engine_b.yolo_verify import (
    YOLOSegmentationVerifier,
    yolo_verifier,
    CUSTOM_FLOOD_CLASSES,
)
from backend.ml.engine_b.cv_water_depth import FloodVisionVerifier, cv_verifier


def _create_synthetic_image_bytes(width: int = 128, height: int = 128, color: tuple = (80, 70, 50)) -> bytes:
    """Helper to generate valid in-memory image bytes using Pillow or standard library PNG generator."""
    if Image is not None:
        img = Image.new("RGB", (width, height), color=color)
        draw = ImageDraw.Draw(img)
        draw.rectangle([int(width * 0.2), int(height * 0.3), int(width * 0.8), int(height * 0.8)], fill=(120, 80, 40))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # Standard-library PNG builder (independent of PIL)
    import zlib, struct
    r, g, b = color
    raw_data = bytearray()
    for _ in range(height):
        raw_data.append(0)  # filter type 0
        raw_data.extend(bytes([r, g, b] * width))
    compressed = zlib.compress(bytes(raw_data))

    png = bytearray(b"\x89PNG\r\n\x1a\n")
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    png.extend(struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc)

    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
    png.extend(struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc)

    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    png.extend(struct.pack(">I", 0) + b"IEND" + iend_crc)
    return bytes(png)


class TestYOLOPipeline:
    """Tests for YOLOSegmentationVerifier."""

    def test_output_structure_on_valid_image(self):
        """Test that detect_flood_features returns the expected structure and keys."""
        img_bytes = _create_synthetic_image_bytes(200, 200)
        res = yolo_verifier.detect_flood_features(img_bytes)

        assert isinstance(res, dict)
        assert "is_valid_image" in res
        assert "flood_detected" in res
        assert "confidence" in res
        assert "detected_objects" in res
        assert "estimated_depth_m" in res
        assert "model_version" in res
        assert "model_source" in res
        assert "inference_time_ms" in res

        assert res["is_valid_image"] is True
        assert isinstance(res["confidence"], (int, float))
        assert isinstance(res["detected_objects"], list)
        assert res["model_source"] in {"custom_flood_model", "pretrained_coco", "heuristic_fallback"}

    def test_corrupted_image_handling(self):
        """Test that invalid/corrupt image bytes are rejected gracefully without exceptions."""
        corrupt_bytes = b"NOT_A_VALID_JPEG_OR_PNG_HEADER_PAYLOAD"
        res = yolo_verifier.detect_flood_features(corrupt_bytes)

        assert isinstance(res, dict)
        assert res["is_valid_image"] is False
        assert res["flood_detected"] is False
        assert res["confidence"] == 0.0
        assert len(res["detected_objects"]) == 0
        assert "error" in res

    def test_low_resolution_image_rejection(self):
        """Test that images smaller than 64x64 are rejected."""
        tiny_bytes = _create_synthetic_image_bytes(32, 32)
        res = yolo_verifier.detect_flood_features(tiny_bytes)

        assert res["is_valid_image"] is False
        assert "resolution" in res.get("error", "").lower()

    def test_missing_model_graceful_handling(self):
        """Test initializing verifier pointing to a non-existent file."""
        verifier = YOLOSegmentationVerifier(model_path="/path/does/not/exist/missing.pt")
        # Should gracefully fallback to pretrained or heuristic without raising an exception
        assert verifier.model_source in {"pretrained_coco", "heuristic_fallback"}

    def test_reported_depth_not_silently_assigned_to_model_depth(self):
        """Verify that citizen reported depth is distinguished from cv_estimated_depth."""
        img_bytes = _create_synthetic_image_bytes(200, 200)
        analysis = cv_verifier.analyze_image_bytes(img_bytes, reported_depth="waist")

        assert analysis["reported_water_depth"] == "waist"
        # Unless a specific reference object was detected, model estimated depth should be None or rule-based
        if not analysis.get("detected_objects"):
            assert analysis["cv_water_depth_m"] is None

    def test_annotation_generator_utility(self):
        """Test that bounding box visualizer executes cleanly."""
        img_bytes = _create_synthetic_image_bytes(200, 200)
        mock_detections = [
            {"class": "submerged_vehicle", "confidence": 0.88, "bbox": [20, 30, 100, 120]}
        ]
        annotated_bytes = yolo_verifier.generate_annotated_image(img_bytes, mock_detections)
        assert isinstance(annotated_bytes, bytes)
        assert len(annotated_bytes) > 0


if __name__ == "__main__":
    pytest.main(["-v", __file__])
