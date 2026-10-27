"""Export the audited VAIPE YOLO splits to COCO without touching source images.

DINO's CocoDetection reader is patched to apply ImageOps.exif_transpose; COCO
width/height and boxes here are in that oriented coordinate system.
"""
import csv
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPLITS = {'train': 'train2017', 'validation': 'val2017', 'test': 'test2017'}


def export(root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    source = root / 'data/processed/vaipe/yolov7'
    target = root / 'data/processed/vaipe/dino_coco'
    (target / 'annotations').mkdir(parents=True, exist_ok=True)
    report = {}
    seen = set()
    groups = {}
    for split, coco_split in SPLITS.items():
        image_dir = target / coco_split
        image_dir.mkdir(parents=True, exist_ok=True)
        with (root / f'data/processed/vaipe/splits/{split}.csv').open(newline='') as f:
            rows = list(csv.DictReader(f))
        images, annotations = [], []
        for image_number, row in enumerate(rows, 1):
            name = row['image_id'] + '.jpg'
            if row['image_id'] in seen or row['validation_errors']:
                raise ValueError(f'duplicate or invalid pair: {name}')
            seen.add(row['image_id'])
            group = row['group_id']
            if group in groups and groups[group] != split:
                raise ValueError(f'group leakage: {group}')
            groups[group] = split
            image_src = source / 'images' / split / name
            label_src = source / 'labels' / split / (row['image_id'] + '.txt')
            if not image_src.is_file() or not label_src.is_file():
                raise FileNotFoundError(name)
            image_dst = image_dir / name
            relative = os.path.relpath(image_src, image_dir)
            if image_dst.is_symlink():
                if os.readlink(image_dst) != relative:
                    raise ValueError(f'wrong symlink: {image_dst}')
            elif image_dst.exists():
                raise ValueError(f'existing non-symlink: {image_dst}')
            else:
                image_dst.symlink_to(relative)
            width, height = int(row['width']), int(row['height'])
            images.append({'id': image_number, 'file_name': name, 'width': width, 'height': height})
            lines = label_src.read_text().splitlines()
            if len(lines) != int(row['box_count']):
                raise ValueError(f'box count mismatch: {name}')
            for line in lines:
                cls, cx, cy, nw, nh = map(float, line.split())
                if cls != 0:
                    raise ValueError(f'non-pill class: {name}')
                x, y = (cx - nw / 2) * width, (cy - nh / 2) * height
                w, h = nw * width, nh * height
                if w <= 0 or h <= 0 or x < -0.01 or y < -0.01 or x+w > width+0.01 or y+h > height+0.01:
                    raise ValueError(f'invalid bbox: {name}')
                annotations.append({'id': len(annotations)+1, 'image_id': image_number,
                                    'category_id': 0, 'bbox': [x,y,w,h], 'area': w*h, 'iscrowd': 0})
        payload = {'images': images, 'annotations': annotations,
                   'categories': [{'id': 0, 'name': 'pill', 'supercategory': 'pill'}]}
        ann_name = f'instances_{coco_split}.json'
        if split == 'validation': ann_name = 'instances_val2017.json'
        (target / 'annotations' / ann_name).write_text(json.dumps(payload, separators=(',', ':')))
        report[split] = {'images': len(images), 'boxes': len(annotations)}
    (target / 'export-report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    print(json.dumps(export(), indent=2))
