#!/usr/bin/env python3
"""
ML Engine B: YOLOv8 Custom Flood Model Fine-Tuning Pipeline.

Trains an Ultralytics YOLOv8 object detector on labeled flood images to detect:
- flood_water
- waterlogged_road
- submerged_vehicle
- person_in_flood

Exports the trained checkpoint to `backend/models/cv/best_flood_yolo.pt` for live inference.
"""

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("fip.engine_b.train")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fine-tune YOLOv8 on custom urban flood imagery for Flood Intelligence Platform."
    )
    parser.add_argument(
        "--data",
        type=str,
        default="backend/ml/engine_b/data/flood.yaml",
        help="Path to flood dataset YAML configuration."
    )
    parser.add_argument(
        "--weights",
        type=str,
        default="yolov8n.pt",
        help="Base pretrained model weights to initialize transfer learning (e.g. yolov8n.pt, yolov8s.pt)."
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Number of training epochs (default: 50)."
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=16,
        help="Batch size (default: 16)."
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Input image resolution in pixels (default: 640)."
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="Computing device: 'cpu', '0', '0,1', etc. (default: cpu)."
    )
    parser.add_argument(
        "--project",
        type=str,
        default="runs/detect",
        help="Output directory for training runs."
    )
    parser.add_argument(
        "--name",
        type=str,
        default="flood_yolo_run",
        help="Experiment run name."
    )
    parser.add_argument(
        "--export-path",
        type=str,
        default="backend/models/cv/best_flood_yolo.pt",
        help="Destination path to copy best weights after training."
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=20,
        help="Early stopping patience in epochs (default: 20)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check dataset config and paths without running actual training."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logger.info("Starting Flood Intelligence YOLO Training Pipeline...")
    logger.info(f"Dataset config: {args.data}")
    logger.info(f"Base weights:   {args.weights}")
    logger.info(f"Target export:  {args.export_path}")

    # 1. Verify Dataset YAML exists
    data_path = Path(args.data)
    if not data_path.is_file():
        logger.error(f"Dataset configuration file not found at: {data_path.resolve()}")
        logger.info("Please create the dataset YAML per backend/ml/engine_b/data/flood.yaml")
        sys.exit(1)

    if args.dry_run:
        logger.info("Dry run check: Dataset config file verified successfully.")
        return

    # 2. Check Ultralytics import
    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error(
            "Ultralytics is not installed. Please install required dependencies:\n"
            "    pip install ultralytics opencv-python-headless Pillow"
        )
        sys.exit(1)

    # 3. Load base model
    logger.info(f"Initializing base YOLO model from '{args.weights}'...")
    try:
        model = YOLO(args.weights)
    except Exception as exc:
        logger.error(f"Failed to load base weights '{args.weights}': {exc}")
        sys.exit(1)

    # 4. Train model
    logger.info(f"Beginning training on '{args.data}' for {args.epochs} epochs (batch={args.batch}, imgsz={args.imgsz})...")
    try:
        train_results = model.train(
            data=str(data_path),
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            device=args.device,
            project=args.project,
            name=args.name,
            patience=args.patience,
            save=True,
            val=True,
            plots=True,
            verbose=True
        )
    except Exception as exc:
        logger.error(f"Training failed with error: {exc}")
        sys.exit(1)

    # 5. Run validation to obtain final metrics
    logger.info("Evaluating model on validation split...")
    try:
        val_results = model.val(data=str(data_path), imgsz=args.imgsz, device=args.device)
        metrics = getattr(val_results, "results_dict", {})
        logger.info("Validation Results Summary:")
        for k, v in metrics.items():
            logger.info(f"  {k}: {v}")
    except Exception as exc:
        logger.warning(f"Validation evaluation warning: {exc}")

    # 6. Locate best weights and export
    run_dir = Path(train_results.save_dir) if hasattr(train_results, "save_dir") else Path(args.project) / args.name
    best_weights_path = run_dir / "weights" / "best.pt"

    if best_weights_path.is_file():
        export_target = Path(args.export_path)
        export_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(best_weights_path, export_target)
        logger.info(f"SUCCESS: Best weights saved and exported to: {export_target.resolve()}")
        logger.info(f"To activate these weights in FIP, set:\n    export FLOOD_YOLO_MODEL_PATH={export_target}")
    else:
        logger.warning(
            f"Could not locate 'best.pt' at {best_weights_path}. Check {run_dir} for output checkpoints."
        )


if __name__ == "__main__":
    main()
