# Computer Vision Pipeline: Real Ultralytics YOLO Integration

This guide demonstrates the upgraded Computer Vision (CV) subsystem of the **Flood Intelligence Platform (FIP)**. The pipeline replaces heuristic image processing with a real **Ultralytics YOLO** deep learning object detection architecture.

---

## 1. Architecture Overview

```
                        Citizen Photo Upload
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ POST /v1/reports        │
                    │ POST /v1/reports/cv-test│
                    └────────────┬────────────┘
                                 │ image bytes
                                 ▼
                 backend/ml/engine_b/cv_water_depth.py
                   (FloodVisionVerifier)
                                 │
                                 ▼
                 backend/ml/engine_b/yolo_verify.py
                 (YOLOSegmentationVerifier Singleton)
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
                 ▼                               ▼
     ┌────────────────────────┐      ┌────────────────────────┐
     │  Custom Flood Model    │      │  Pretrained COCO YOLO  │
     │ (best_flood_yolo.pt)   │  OR  │     (yolov8n.pt)       │
     │                        │      │                        │
     │ Classes:               │      │ Proxies:               │
     │ - flood_water          │      │ - boat                 │
     │ - waterlogged_road     │      │ - car / truck / bus    │
     │ - submerged_vehicle    │      │ - person               │
     │ - person_in_flood      │      │                        │
     └───────────┬────────────┘      └───────────┬────────────┘
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼
                    Structured Detection Output:
                    - is_valid_image (bool)
                    - cv_verified (bool)
                    - water_detected (bool)
                    - cv_confidence (float)
                    - detected_objects ([{class, confidence, bbox}])
                    - cv_water_depth_m (float | null)
                    - reported_water_depth (str)
                    - model_source & model_version
```

---

## 2. Model Operational Modes

The platform dynamically detects the active model environment without downtime:

| Mode (`model_source`) | Description | Target Classes |
|:---|:---|:---|
| `custom_flood_model` | Fine-tuned on urban flood dataset at `FLOOD_YOLO_MODEL_PATH` | `flood_water`, `waterlogged_road`, `submerged_vehicle`, `person_in_flood` |
| `pretrained_coco` | Standard lightweight `yolov8n.pt` initialized out-of-the-box | Street objects (`car`, `truck`, `person`, `boat`) as urban flood proxies |
| `heuristic_fallback` | Active if Ultralytics/PyTorch is unavailable in minimal runtimes | Resolution, header, and color profile analysis |

---

## 3. Test Endpoint: `POST /v1/reports/cv-test`

The direct evaluation endpoint allows immediate verification without writing rows to the PostgreSQL database.

### `curl` Example

```bash
curl -X POST "http://localhost:8000/v1/reports/cv-test" \
  -H "Accept: application/json" \
  -F "image=@/path/to/flood_scene.jpg" \
  -F "reported_depth=waist" \
  -F "return_annotated_image=false"
```

### Sample JSON Response (Custom Flood Model)

```json
{
  "is_valid_image": true,
  "cv_verified": true,
  "water_detected": true,
  "cv_confidence": 0.914,
  "detected_objects": [
    {
      "class": "submerged_vehicle",
      "confidence": 0.884,
      "bbox": [112.5, 230.1, 480.0, 520.4]
    },
    {
      "class": "flood_water",
      "confidence": 0.914,
      "bbox": [0.0, 310.0, 640.0, 640.0]
    }
  ],
  "detected_landmarks": [
    "submerged_vehicle",
    "flood_water"
  ],
  "cv_water_depth_m": 0.85,
  "reported_water_depth": "waist",
  "cv_estimated_depth_category": "submerged",
  "model_version": "custom-flood-best_flood_yolo",
  "model_source": "custom_flood_model",
  "inference_time_ms": 28.4,
  "reason": "Verified via custom flood model: detected 2 flood instances."
}
```

### Sample JSON Response (Pretrained COCO Mode)

```json
{
  "is_valid_image": true,
  "cv_verified": true,
  "water_detected": true,
  "cv_confidence": 0.85,
  "detected_objects": [
    {
      "class": "car",
      "confidence": 0.852,
      "bbox": [120.0, 240.0, 450.0, 480.0]
    }
  ],
  "detected_landmarks": [
    "car"
  ],
  "cv_water_depth_m": null,
  "reported_water_depth": "knee",
  "cv_estimated_depth_category": null,
  "model_version": "yolov8n-pretrained-coco",
  "model_source": "pretrained_coco",
  "inference_time_ms": 24.1,
  "reason": "Pretrained COCO model detected street objects (vehicles/people) co-located with water surface reflections. Note: Standard COCO lacks 'flood_water' class; fine-tuning recommended."
}
```

---

## 4. Distinction Between Reported and Model Depth

The platform enforces strict scientific distinction:
- **`reported_water_depth`**: The citizen's subjective label (`ankle`, `knee`, `waist`, `submerged`).
- **`cv_water_depth_m`**: Quantitative estimate derived **only** when defensible landmark reference rules are triggered (e.g. `submerged_vehicle` -> `0.85m`). If no reference landmark occlusion is recognized, `cv_water_depth_m` returns `null`.

---

## 5. How to Train a Custom Flood YOLO Model

1. **Install ML Dependencies**:
   ```bash
   pip install ultralytics opencv-python-headless Pillow
   ```

2. **Prepare Dataset**:
   Organize images and YOLO format label files according to `backend/ml/engine_b/data/flood.yaml`:
   ```
   dataset/
   ├── images/
   │   ├── train/
   │   └── val/
   └── labels/
       ├── train/
       └── val/
   ```

3. **Launch Fine-Tuning**:
   ```bash
   python backend/ml/engine_b/train_flood_yolo.py \
     --data backend/ml/engine_b/data/flood.yaml \
     --weights yolov8n.pt \
     --epochs 50 \
     --batch 16 \
     --imgsz 640 \
     --device cpu \
     --export-path backend/models/cv/best_flood_yolo.pt
   ```

4. **Activate the Model**:
   Update your environment or `.env`:
   ```bash
   export FLOOD_YOLO_MODEL_PATH=backend/models/cv/best_flood_yolo.pt
   ```
   The application will automatically detect the presence of `best_flood_yolo.pt` and switch `model_source` to `custom_flood_model`.

---

## 6. Valid vs. Invalid Image Behavior

- **Corrupted Image / Random Bytes**: Returns HTTP 200 with `"is_valid_image": false`, `"confidence": 0.0`, and an explanatory error message.
- **Low Resolution (<64x64 px)**: Rejected with `"is_valid_image": false` and `"error": "Image resolution ... is below minimum requirement (64x64 pixels)."`.
- **Missing Model Checkpoint**: Falls back seamlessly to pretrained weights or fallback mode; service does not crash.
