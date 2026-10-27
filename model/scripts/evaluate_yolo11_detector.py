"""Export YOLO11s detections and compare with YOLOv7 using one COCOeval.

Run validation first. Run held-out test once after the validation-selected best.pt
is frozen; this script never tunes a score threshold using the test set.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from pycocotools.coco import COCO
from ultralytics import YOLO

from audit_pill_rois import audit
from compare_pill_detectors_coco import evaluate

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / 'model/runs/detector'
DATA = ROOT / 'data/processed/vaipe/dino_coco'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['validation', 'test'], required=True)
    parser.add_argument('--run-name', default='yolo11s_pill_20261027')
    parser.add_argument('--device', default='0')
    args = parser.parse_args()
    part = 'val' if args.split == 'validation' else 'test'
    gt_path = DATA / f'annotations/instances_{part}2017.json'
    run = RUNS / args.run_name
    weights = run / 'weights/best.pt'
    previous = RUNS / ('yolov7_pill_recognition_validation' if part == 'val'
        else 'yolov7_pill_common_eval') / 'best_predictions.json'
    predictions_path = run / f'predictions-{part}.json'
    metrics_path = run / f'metrics-{part}.json'
    if predictions_path.exists() or metrics_path.exists():
        raise FileExistsError('Evaluation output already exists; do not re-tune on the same split')
    if not weights.is_file() or not previous.is_file():
        raise FileNotFoundError('Missing YOLO11 best.pt or YOLOv7 baseline predictions')
    coco = COCO(str(gt_path))
    images = coco.imgs
    source = DATA / f'{part}2017'
    name_to_id = {info['file_name']: image_id for image_id, info in images.items()}
    if any(not (source / name).is_file() for name in name_to_id):
        raise FileNotFoundError('Missing COCO evaluation image')
    model = YOLO(str(weights))
    detections = []
    speeds = defaultdict(float)
    seen = set()
    count = 0
    for result in model.predict(source=str(source), stream=True,
            imgsz=640, batch=8, conf=.001, iou=.65, max_det=300,
            device=args.device, half=args.device != 'cpu', verbose=False):
        name = Path(result.path).name
        if name not in name_to_id:
            raise ValueError(f'Unexpected evaluation image: {name}')
        image_id = name_to_id[name]
        if image_id in seen:
            raise ValueError(f'Duplicate evaluation image: {name}')
        seen.add(image_id)
        info = images[image_id]
        if result.orig_shape != (info['height'], info['width']):
            raise ValueError(f'Image order/orientation mismatch: {result.path}')
        for xyxy, score, cls in zip(result.boxes.xyxy.cpu().tolist(),
                result.boxes.conf.cpu().tolist(), result.boxes.cls.cpu().tolist(), strict=True):
            if int(cls) != 0:
                raise ValueError('Unexpected non-pill class')
            x1, y1, x2, y2 = xyxy
            detections.append({'image_id': image_id, 'category_id': 0,
                'bbox': [x1, y1, x2-x1, y2-y1], 'score': float(score)})
        for key, value in result.speed.items():
            speeds[key] += value
        count += 1
        if count % 200 == 0:
            print(f'{part}: {count}/{len(images)} images', flush=True)
    if count != len(images):
        raise ValueError(f'Missing images: {count}/{len(images)}')
    predictions_path.write_text(json.dumps(detections) + '\n')
    stem_to_id = {info['file_name'].rsplit('.', 1)[0]: image_id
        for image_id, info in images.items()}
    same_protocol = [evaluate(coco, 'yolov7', previous, stem_to_id),
        evaluate(coco, 'yolo11s', predictions_path, stem_to_id)]
    raw = json.loads(gt_path.read_text())
    by_image = defaultdict(list)
    for item in raw['annotations']:
        by_image[item['image_id']].append(item)
    roi_audit = [audit('yolov7', json.loads(previous.read_text()), images, by_image)[0],
        audit('yolo11s', detections, images, by_image)[0]]
    payload = {'split': args.split, 'images': count, 'gt_boxes': len(coco.anns),
        'checkpoint_selection': 'best.pt selected by validation only',
        'inference': {'imgsz': 640, 'batch': 8, 'conf': .001, 'iou_nms': .65,
            'max_det': 300, 'device': args.device, 'half': args.device != 'cpu'},
        'source_sha256': {'yolo11_best': sha256(weights),
            'ground_truth': sha256(gt_path), 'yolov7_predictions': sha256(previous)},
        'coco_eval': same_protocol, 'diagnostic_roi_cutoff_025': roi_audit,
        'yolo11_speed_ms_per_image': {k: v / count for k, v in speeds.items()},
        'test_used_for_selection': False}
    metrics_path.write_text(json.dumps(payload, indent=2) + '\n')
    print(json.dumps(payload, indent=2), flush=True)


if __name__ == '__main__':
    main()
