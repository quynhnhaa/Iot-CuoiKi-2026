"""Diagnostic YOLOv7 pill counts on unassigned local phone photos, CPU only."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import torch

from infer_yolov7_cpu_safe import CHECKPOINT, CONFIDENCE, detect, load_detector

ROOT = Path(__file__).resolve().parents[2]
CAPTURED = ROOT / 'data/captured'


def main():
    torch.set_num_threads(8)
    with (CAPTURED / 'inventory.csv').open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    if not rows or any(row['split'] != 'unassigned' for row in rows):
        raise ValueError('Pilot detector requires non-empty unassigned inventory')
    model = load_detector()
    records = []
    counts = Counter()
    by_label = defaultdict(Counter)
    for row in rows:
        path = ROOT / row['image_path']
        if not path.resolve().is_relative_to(CAPTURED.resolve()) or not path.is_file():
            raise ValueError(f'Image missing/outside captured: {path}')
        response = detect(model, path)
        n = len(response['detections'])
        route = 'zero' if n == 0 else 'one' if n == 1 else 'multiple'
        counts[route] += 1
        by_label[f"{row['filename_drug_name']}/{row['filename_condition']}"][route] += 1
        records.append({'image_path': row['image_path'],
            'filename_drug_name': row['filename_drug_name'],
            'filename_condition': row['filename_condition'],
            'source_sha256': row['sha256'], 'detected_count': n,
            'detections': response['detections'], 'timing_ms': response['timing_ms']})
        print(path.name, route, [round(x['score'], 3) for x in response['detections']], flush=True)
    payload = {'status': 'diagnostic_only', 'source': 'phone photos, not machine camera',
        'threshold': CONFIDENCE, 'checkpoint_sha256': hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest(),
        'images': len(records), 'count_routes': dict(counts),
        'filename_label_routes': {key: dict(value) for key, value in sorted(by_label.items())},
        'records': records, 'identity_or_defect_accuracy_measured': False,
        'release_allowed': False}
    (CAPTURED / 'pilot-detector-results.json').write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('summary', json.dumps(payload['count_routes']), flush=True)


if __name__ == '__main__':
    main()
