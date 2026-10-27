"""Fail-closed CPU replay through YOLOv7, PIM, verifier and defect models.

This is diagnostic replay, not camera/actuator integration.
The unvalidated identity gate is forced closed for every image.
"""
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'model/scripts'))
sys.path.insert(0, str(ROOT / 'model/src'))
from common.decision_simulator import Observation, decide  # noqa: E402
from export_recognition_rois import crop_box  # noqa: E402
from finetune_pharmavision_cpu import model_for_training  # noqa: E402
from train_recognition_pim import CLASSES, build_model  # noqa: E402
from train_recognition_verifier import Verifier  # noqa: E402

SPLIT = ROOT / 'data/processed/vaipe/splits/validation.csv'
DETECTIONS = ROOT / 'model/runs/detector/yolov7_pill_recognition_validation/best_predictions.json'
PIM = ROOT / 'model/runs/recognition/pim_resnet50_7class_20261026_v2/best.pt'
VERIFIER = ROOT / 'model/runs/recognition/class_conditioned_verifier_20261027/best.pt'
VERIFIER_META = VERIFIER.parent / 'validation-results.json'
DEFECT = ROOT / 'model/runs/defect/efficientnetv2s_finalblocks_cpu_20261027/best.pt'
DETECTOR = ROOT / 'model/runs/detector/yolov7_pill_baseline_20261025_v2/weights/best.pt'
RUNS = ROOT / 'model/runs/pipeline'
DETECTOR_CONF = 0.25  # Replay filter from YOLOv7 detect.py; not a validated operating threshold.
EMPTY_ID = 'synthetic_empty_640'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_checkpoint(path):
    # Only NumPy array/dtype primitives from our locally trained checkpoint are allowlisted.
    from numpy._core.multiarray import _reconstruct
    allowed = [_reconstruct, np.ndarray, np.dtype,
               type(np.dtype('uint32')), type(np.dtype('float32')), type(np.dtype('float64'))]
    unsafe = set(torch.serialization.get_unsafe_globals_in_checkpoint(path))
    expected = {'numpy._core.multiarray._reconstruct', 'numpy.dtype', 'numpy.ndarray'}
    if not unsafe.issubset(expected):
        raise ValueError(f'unexpected checkpoint globals: {sorted(unsafe - expected)}')
    with torch.serialization.safe_globals(allowed):
        return torch.load(path, map_location='cpu', weights_only=True)


def load_models():
    pim_checkpoint = safe_checkpoint(PIM)
    pim = build_model(pim_checkpoint['config'], load_imagenet=False)
    pim.load_state_dict(pim_checkpoint['model'])
    pim.eval()
    verifier_checkpoint = safe_checkpoint(VERIFIER)
    verifier = Verifier()
    verifier.load_state_dict(verifier_checkpoint['model'])
    verifier.eval()
    defect_checkpoint = safe_checkpoint(DEFECT)
    if defect_checkpoint['epoch'] != 11:
        raise ValueError('defect checkpoint must be best epoch 12')
    defect = model_for_training()
    defect.load_state_dict(defect_checkpoint['model'])
    defect.eval()
    return pim, verifier, defect


class DetectorWorker:
    def __init__(self, stderr_path):
        self.stderr = stderr_path.open('w')
        self.process = subprocess.Popen(
            [sys.executable, '-u', str(ROOT / 'model/scripts/infer_yolov7_cpu_safe.py')],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
            text=True, bufsize=1, cwd=ROOT)
        line = self.process.stdout.readline()
        if not line or not json.loads(line).get('ready'):
            raise RuntimeError(f'detector worker failed to start; see {stderr_path}')

    def detect(self, path):
        start = time.perf_counter()
        self.process.stdin.write(json.dumps({'image_path': str(path)}) + '\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('detector worker exited; inspect detector-stderr.log')
        response = json.loads(line)
        response['wall_ms'] = (time.perf_counter() - start) * 1000
        return response

    def close(self):
        if self.process.stdin:
            self.process.stdin.close()
        self.process.wait(timeout=10)
        self.stderr.close()
        if self.process.returncode:
            raise RuntimeError(f'detector worker failed with code {self.process.returncode}')


def load_replay_inputs():
    with SPLIT.open(newline='') as f:
        rows = {r['image_id']: r for r in csv.DictReader(f)}
    boxes = defaultdict(list)
    for item in json.loads(DETECTIONS.read_text()):
        if item['image_id'] not in rows or item['category_id'] != 0:
            raise ValueError('detector export has unexpected image or category')
        boxes[item['image_id']].append(item)
    return rows, boxes


def model_inputs(roi):
    norm = transforms.Normalize([.485, .456, .406], [.229, .224, .225])
    pim_input = transforms.Compose([transforms.Resize((360, 360)),
                                    transforms.CenterCrop(320), transforms.ToTensor(), norm])(roi)
    defect_input = transforms.Compose([transforms.Resize(224),
                                       transforms.CenterCrop(224), transforms.ToTensor(), norm])(roi)
    return pim_input.unsqueeze(0), defect_input.unsqueeze(0)


def replay_one(row, exported, target_id, models, calibration, detector=None):
    start = time.perf_counter()
    image_path = ROOT / row['image_path']
    with Image.open(image_path) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB')
    image_loaded = time.perf_counter()
    if image.size != (int(row['width']), int(row['height'])):
        raise ValueError(f'EXIF dimension mismatch: {image_path}')
    worker_result = detector.detect(image_path) if detector is not None else None
    detections = worker_result['detections'] if worker_result is not None else exported
    selected = sorted((b for b in detections if b['score'] >= DETECTOR_CONF),
                      key=lambda b: b['score'], reverse=True)
    detector_replayed = time.perf_counter()
    result = {'image_id': row['image_id'], 'image_path': row['image_path'],
              'image_sha256': sha(image_path), 'selected_target_id': target_id,
              'detector_source': 'YOLOv7 checkpoint CPU inference' if detector is not None else
                                 'exported YOLOv7 validation predictions; no live detector inference',
              'detector_conf_filter': DETECTOR_CONF, 'detected_pill_count': len(selected),
              'detections': [{'bbox_xywh': b['bbox'], 'score': b['score']} for b in selected],
              'timing_ms': {'image_decode': (image_loaded - start) * 1000,
                            ('detector_worker_wall' if detector is not None else 'detector_export_lookup'):
                                (detector_replayed - image_loaded) * 1000}}
    if worker_result is not None:
        result['timing_ms']['detector_model_preprocess_inference_nms'] = worker_result['timing_ms']['preprocess_inference_nms']
        result['timing_ms']['detector_worker_decode'] = worker_result['timing_ms']['decode']
    if len(selected) != 1:
        decision_start = time.perf_counter()
        decision = decide(Observation(len(selected), True, False, False, 'uncertain'))
        done = time.perf_counter()
        result['stages_skipped'] = ['roi', 'recognition', 'verifier', 'defect']
        result['timing_ms']['decision'] = (done - decision_start) * 1000
    else:
        crop_start = time.perf_counter()
        box = crop_box(selected[0]['bbox'], image.width, image.height)
        roi = image.crop(box)
        pim_input, defect_input = model_inputs(roi)
        crop_done = time.perf_counter()
        pim, verifier, defect = models
        features = []
        hook = pim.combiner.dropout.register_forward_hook(
            lambda _m, _i, out: features.append(out.detach().flatten(1)))
        with torch.inference_mode():
            logits = pim(pim_input)['comb_outs']
        hook.remove()
        recognition_done = time.perf_counter()
        if len(features) != 1:
            raise RuntimeError('PIM feature hook did not run exactly once')
        classifier = F.softmax(logits / calibration['temperature'], dim=1)[0]
        predicted_index = int(classifier.argmax())
        with torch.inference_mode():
            verification = verifier(F.normalize(features[0], dim=1)).sigmoid()[0]
        diagnostic_score = float(classifier[predicted_index] * verification[predicted_index])
        verifier_done = time.perf_counter()
        with torch.inference_mode():
            defect_probability = float(defect(defect_input).softmax(dim=1)[0, 1])
        defect_done = time.perf_counter()
        defect_status = 'defective' if defect_probability >= 0.40 else 'normal'
        decision_start = time.perf_counter()
        decision = decide(Observation(1, True, False, int(CLASSES[predicted_index]) == target_id,
                                      defect_status, identity_gate_validated=False, hardware_ready=False))
        done = time.perf_counter()
        result.update({'roi_xyxy': box, 'predicted_drug_id': int(CLASSES[predicted_index]),
                       'recognition_probability': float(classifier[predicted_index]),
                       'verifier_diagnostic_score': diagnostic_score,
                       'verifier_diagnostic_threshold': calibration['threshold'],
                       'identity_verified': False,
                       'identity_note': 'open-set gate not validated; diagnostic score never authorizes routing',
                       'defective_probability': defect_probability, 'defect_status': defect_status})
        result['timing_ms'].update({'roi_and_preprocess': (crop_done - crop_start) * 1000,
                                    'recognition': (recognition_done - crop_done) * 1000,
                                    'verifier': (verifier_done - recognition_done) * 1000,
                                    'defect': (defect_done - verifier_done) * 1000,
                                    'decision': (done - decision_start) * 1000})
    result['timing_ms']['total_from_image_decode'] = (done - start) * 1000
    result['decision'] = {'route': decision.route, 'release_allowed': decision.release_allowed,
                          'accepted_count_increment': decision.accepted_count_increment,
                          'reason': decision.reason}
    if decision.release_allowed or decision.accepted_count_increment:
        raise RuntimeError('dry-run safety invariant violated')
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-name', required=True)
    p.add_argument('--target-id', type=int, required=True)
    p.add_argument('--image-id', action='append', required=True)
    p.add_argument('--threads', type=int, default=8)
    p.add_argument('--live-detector', action='store_true',
                   help='Run YOLOv7 CPU worker using weights_only safe allowlist')
    p.add_argument('--include-empty-frame', action='store_true',
                   help='Append a generated blank image for a no-pill control case')
    args = p.parse_args()
    if args.target_id not in CLASSES:
        raise ValueError(f'target must be one of {CLASSES}')
    if not args.run_name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-' for c in args.run_name):
        raise ValueError('invalid run name')
    if args.threads < 1 or len(set(args.image_id)) != len(args.image_id):
        raise ValueError('invalid threads or duplicate image ID')
    if args.include_empty_frame and not args.live_detector:
        raise ValueError('empty-frame control requires live detector')
    run = RUNS / args.run_name
    if run.exists():
        raise FileExistsError(run)
    torch.set_num_threads(args.threads)
    rows, boxes = load_replay_inputs()
    for image_id in args.image_id:
        if image_id not in rows:
            raise ValueError(f'image is not in VAIPE validation split: {image_id}')
    image_ids = list(args.image_id)
    models = load_models()
    calibration = json.loads(VERIFIER_META.read_text())
    run.mkdir(parents=True)
    if args.include_empty_frame:
        blank = run / 'synthetic-empty.png'
        Image.new('RGB', (640, 640), (128, 128, 128)).save(blank)
        rows[EMPTY_ID] = {'image_id': EMPTY_ID, 'image_path': str(blank.relative_to(ROOT)),
                          'width': '640', 'height': '640'}
        boxes[EMPTY_ID] = []
        image_ids.append(EMPTY_ID)
    manifest = {'mode': 'model_replay_cpu_no_actuation' if args.live_detector else 'artifact_replay_cpu_no_actuation',
                'target_id': args.target_id,
                'image_ids': image_ids, 'detector_conf_filter': DETECTOR_CONF,
                'source_sha256': {str(x.relative_to(ROOT)): sha(x) for x in
                                  ((SPLIT, DETECTOR, PIM, VERIFIER, DEFECT) if args.live_detector else
                                   (SPLIT, DETECTIONS, PIM, VERIFIER, DEFECT))},
                'identity_gate_validated': False, 'hardware_ready': False}
    (run / 'run-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    detector = DetectorWorker(run / 'detector-stderr.log') if args.live_detector else None
    try:
        records = [replay_one(rows[image_id], boxes[image_id], args.target_id, models, calibration, detector)
                   for image_id in image_ids]
    finally:
        if detector is not None:
            detector.close()
    with (run / 'events.jsonl').open('w') as f:
        for record in records:
            f.write(json.dumps(record) + '\n')
    summary = {'image_count': len(records), 'routes': {route: sum(r['decision']['route'] == route for r in records)
                                                     for route in ('EMPTY_FRAME', 'MULTIPLE_PILLS', 'WRONG_DRUG', 'DEFECTIVE', 'ACCEPTED')},
               'release_command_count': sum(r['decision']['release_allowed'] for r in records),
               'accepted_count_increment': sum(r['decision']['accepted_count_increment'] for r in records),
               'total_timing_ms': [r['timing_ms']['total_from_image_decode'] for r in records],
               'detector_is_export_replay': not args.live_detector, 'identity_gate_validated': False}
    (run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
