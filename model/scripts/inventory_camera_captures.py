"""Inventory local camera photos without treating filename labels as verified truth."""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
CAPTURED = ROOT / 'data/captured'
PATTERN = re.compile(r'(?P<drug>.+)_(?P<state>[ox])_(?P<number>\d+)$')
FIELDS = ('image_path', 'filename_drug_name', 'filename_condition',
          'filename_sequence', 'width', 'height', 'exif_orientation',
          'exif_datetime', 'exif_camera_model', 'sha256', 'readable',
          'identity_evidence_ref', 'split')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(folder):
    rows = []
    hashes = defaultdict(list)
    errors = []
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in {'.jpg', '.jpeg'}:
            continue
        match = PATTERN.fullmatch(path.stem)
        if not match:
            errors.append(f'Unexpected filename pattern: {path.name}')
        width = height = orientation = exif_datetime = exif_camera_model = ''
        readable = False
        try:
            with Image.open(path) as raw:
                exif = raw.getexif()
                orientation = exif.get(274, 1)
                exif_datetime = exif.get(306) or exif.get(36867) or ''
                exif_camera_model = exif.get(272) or ''
                image = ImageOps.exif_transpose(raw)
                image.load()
                width, height = image.size
                readable = width >= 64 and height >= 64
        except (OSError, ValueError) as exc:
            errors.append(f'Unreadable image {path.name}: {exc}')
        if not readable:
            errors.append(f'Image too small or unreadable: {path.name}')
        digest = sha256(path)
        hashes[digest].append(path.name)
        rows.append({'image_path': str(path.relative_to(ROOT)),
            'filename_drug_name': match['drug'] if match else '',
            'filename_condition': {'o': 'normal', 'x': 'defective'}[match['state']] if match else 'unknown',
            'filename_sequence': match['number'] if match else '',
            'width': width, 'height': height, 'exif_orientation': orientation,
            'exif_datetime': exif_datetime, 'exif_camera_model': exif_camera_model,
            'sha256': digest, 'readable': readable,
            'identity_evidence_ref': '', 'split': 'unassigned'})
    duplicates = [names for names in hashes.values() if len(names) > 1]
    if duplicates:
        errors.append(f'Duplicate image bytes: {duplicates}')
    counts = Counter((r['filename_drug_name'], r['filename_condition']) for r in rows)
    summary = {'image_count': len(rows), 'readable_count': sum(r['readable'] for r in rows),
        'dimensions': dict(Counter(f"{r['width']}x{r['height']}" for r in rows)),
        'filename_label_counts': {f'{drug}/{condition}': count
            for (drug, condition), count in sorted(counts.items())},
        'duplicate_sha256_groups': duplicates, 'errors': errors,
        'label_source': 'filename only; operator reports package/lot cross-check, evidence reference and physical-pill grouping not yet recorded',
        'all_splits': 'unassigned'}
    return rows, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path, default=CAPTURED)
    args = parser.parse_args()
    rows, summary = inventory(args.folder)
    with (args.folder / 'inventory.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (args.folder / 'inventory-summary.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if errors := summary['errors']:
        raise SystemExit(f'{len(errors)} inventory errors')


if __name__ == '__main__':
    main()
