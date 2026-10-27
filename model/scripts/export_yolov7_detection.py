"""Export VAIPE group-safe splits to YOLOv7's images/labels layout.

Original images and JSON labels are never modified. Images are relative symlinks;
labels are one-class YOLO TXT files using EXIF-oriented image dimensions.
"""
import csv
import json
import os
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPLITS = ('train', 'validation', 'test')


def convert_box(box: dict, width: int, height: int) -> str:
    x, y, w, h = (box[key] for key in ('x', 'y', 'w', 'h'))
    if not (width > 0 and height > 0 and x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= width and y + h <= height):
        raise ValueError(f'invalid box: {box} in {width}x{height}')
    values = ((x + w / 2) / width, (y + h / 2) / height, w / width, h / height)
    if not all(0 <= value <= 1 for value in values):
        raise ValueError(f'box normalization failed: {box}')
    return '0 ' + ' '.join(f'{value:.8f}' for value in values)


def export(root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    output = root / 'data/processed/vaipe/yolov7'
    excluded_file = root / 'data/processed/vaipe/excluded-invalid-pairs.csv'
    with excluded_file.open(newline='') as stream:
        excluded = {row['image_id'] for row in csv.DictReader(stream)}
    counts = {}
    seen_ids = set()
    group_locations = {}
    for split in SPLITS:
        with (root / f'data/processed/vaipe/splits/{split}.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        image_dir = output / 'images' / split
        label_dir = output / 'labels' / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        box_count = 0
        for row in rows:
            image_id = row['image_id']
            if image_id in excluded or image_id in seen_ids or row['validation_errors']:
                raise ValueError(f'excluded, duplicate, or invalid image: {image_id}')
            seen_ids.add(image_id)
            group = row['group_id']
            if group in group_locations and group_locations[group] != split:
                raise ValueError(f'group leakage: {group}')
            group_locations[group] = split
            source_image = root / row['image_path']
            source_label = root / row['label_path']
            if not source_image.is_file() or not source_label.is_file():
                raise FileNotFoundError(image_id)
            destination_image = image_dir / source_image.name
            relative_source = os.path.relpath(source_image, image_dir)
            if destination_image.is_symlink():
                if os.readlink(destination_image) != relative_source:
                    raise ValueError(f'wrong existing symlink: {destination_image}')
            elif destination_image.exists():
                raise ValueError(f'existing file is not a symlink: {destination_image}')
            else:
                destination_image.symlink_to(relative_source)
            boxes = json.loads(source_label.read_text(encoding='utf-8'))
            if len(boxes) != int(row['box_count']):
                raise ValueError(f'box count mismatch: {image_id}')
            lines = [convert_box(box, int(row['width']), int(row['height'])) for box in boxes]
            (label_dir / f'{image_id}.txt').write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
            box_count += len(lines)
        counts[split] = {'images': len(rows), 'boxes': box_count, 'groups': len({r['group_id'] for r in rows})}
    # Absolute paths are explicit because YOLOv7 may be launched from any directory.
    yaml = 'train: ' + str(output / 'images/train') + '\n'
    yaml += 'val: ' + str(output / 'images/validation') + '\n'
    yaml += 'test: ' + str(output / 'images/test') + '\n'
    yaml += 'nc: 1\nnames: [pill]\n'
    (output / 'pill.yaml').write_text(yaml, encoding='utf-8')
    metadata = {'format': 'YOLOv7 one-class detection', 'split_seed': 20261025, 'excluded_pair_count': len(excluded), 'counts': counts, 'source': 'VAIPE public_train valid pairs', 'exif_note': 'Normalized labels use EXIF-oriented dimensions; verify the training image loader honors EXIF orientation.'}
    (output / 'export-report.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return metadata


if __name__ == '__main__':
    print(json.dumps(export(), indent=2))
