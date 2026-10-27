"""Index detector-matched VAIPE labels outside the seven recognition IDs.

The output points to original images and crop coordinates; it does not copy images.
Unknown train may be used to learn rejection; validation selects the operating
point, and test remains reserved for final evaluation.
Warning: VAIPE label 107 means out-of-prescription in context, not a verified
new pill identity. Use filter_vaipe_context_unknown.py before appearance-based
open-set training or evaluation.
"""
import csv
import json
from collections import Counter, defaultdict

from export_recognition_rois import ROOT, SELECTED, PRED, match, crop_box
from PIL import Image, ImageOps


def main():
    base = ROOT / 'data/processed/vaipe/recognition/yolov7_unknown'
    base.mkdir(parents=True, exist_ok=True)
    report = {'known_ids': SELECTED, 'match_iou': 0.5,
              'context_label_107_is_not_identity_unknown': True, 'splits': {}}
    fields = ['image_id', 'annotation_index', 'class_id', 'group_id', 'image_path',
              'detector_score', 'match_iou', 'crop_left', 'crop_top', 'crop_right', 'crop_bottom']
    groups = {}
    for split in ('train', 'validation', 'test'):
        with (ROOT / f'data/processed/vaipe/splits/{split}.csv').open(newline='') as f:
            rows = list(csv.DictReader(f))
        predictions = defaultdict(list)
        for item in json.loads(PRED[split].read_text()):
            predictions[item['image_id']].append(item)
        output = []
        expected = Counter()
        matched_counts = Counter()
        for row in rows:
            image_id, group = row['image_id'], row['group_id']
            if group in groups and groups[group] != split:
                raise ValueError(f'group leakage: {group}')
            groups[group] = split
            labels = json.loads((ROOT / row['label_path']).read_text())
            if len(labels) != int(row['box_count']):
                raise ValueError(f'label count mismatch: {image_id}')
            pairs = match(predictions[image_id], labels)
            image_size = (int(row['width']), int(row['height']))
            for index, label in enumerate(labels):
                cls = int(label['label'])
                if cls in SELECTED:
                    continue
                expected[cls] += 1
                if index not in pairs:
                    continue
                prediction, overlap = pairs[index]
                box = crop_box(prediction['bbox'], *image_size)
                output.append(dict(zip(fields, [image_id, index, cls, group,
                    row['image_path'], prediction['score'], overlap, *box])))
                matched_counts[cls] += 1
        with (base / f'{split}.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fields)
            writer.writeheader()
            writer.writerows(output)
        report['splits'][split] = {
            'expected_boxes': sum(expected.values()), 'matched_rois': len(output),
            'unmatched_boxes': sum(expected.values()) - len(output),
            'class_count': len(matched_counts),
            'class_counts': dict(sorted(matched_counts.items())),
        }
    (base / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['splits'], indent=2))


if __name__ == '__main__':
    main()
