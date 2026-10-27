"""Audit real-camera pill images and guard against split/class leakage (CPU only)."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ('sample_id', 'image_path', 'capture_session_id', 'pill_instance_id',
          'verified_drug_id', 'target_drug_id', 'view', 'condition',
          'identity_evidence_ref', 'camera_id', 'lighting_id', 'split')
SPLITS = {'train', 'validation', 'test', 'unassigned'}
VIEWS = {'front', 'back', 'edge', 'other'}
CONDITIONS = {'normal', 'defective', 'unknown'}


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_known(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    values = data.get('known_drug_ids')
    if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError('known_drug_ids must be a non-empty list of real drug ID strings')
    if len(set(values)) != len(values):
        raise ValueError('known_drug_ids contains duplicates')
    return set(values)


def audit(manifest, known_ids):
    errors, warnings = [], []
    with manifest.open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != FIELDS:
            raise ValueError(f'Manifest columns must be exactly: {",".join(FIELDS)}')
        rows = list(reader)
    if not rows:
        raise ValueError('Manifest has no images; use manifest.template.csv as a starting header')
    sample_ids = set()
    sessions = defaultdict(set)
    instances = defaultdict(set)
    instance_drugs = defaultdict(set)
    image_hashes = defaultdict(list)
    unknown_ids = defaultdict(set)
    split_counts = Counter()
    known_counts = Counter()
    view_counts = Counter()
    condition_counts = Counter()
    camera_counts = Counter()
    for number, row in enumerate(rows, 2):
        prefix = f'row {number}'
        if None in row:
            errors.append(f'{prefix}: too many CSV columns')
            continue
        if any(value is None or not value.strip() for value in row.values()):
            errors.append(f'{prefix}: every field is required')
            continue
        if any(value != value.strip() for value in row.values()):
            errors.append(f'{prefix}: leading/trailing whitespace in a field')
        if row['sample_id'] in sample_ids:
            errors.append(f'{prefix}: duplicate sample_id {row["sample_id"]}')
        sample_ids.add(row['sample_id'])
        split = row['split']
        if split not in SPLITS:
            errors.append(f'{prefix}: invalid split {split}')
            continue
        if row['view'] not in VIEWS:
            errors.append(f'{prefix}: invalid view {row["view"]}')
        if row['condition'] not in CONDITIONS:
            errors.append(f'{prefix}: invalid condition {row["condition"]}')
        if row['target_drug_id'] not in known_ids:
            errors.append(f'{prefix}: target_drug_id is absent from known_drug_ids')
        if row['identity_evidence_ref'].lower() in {'unknown', 'none', 'n/a', '-'}:
            errors.append(f'{prefix}: identity evidence is not recorded')
        image_path = Path(row['image_path'])
        if image_path.is_absolute() or '..' in image_path.parts:
            errors.append(f'{prefix}: image_path must be relative without parent traversal')
            continue
        candidate = (ROOT / image_path).resolve()
        captured_root = (ROOT / 'data/captured').resolve()
        if not candidate.is_relative_to(captured_root) or not candidate.is_file():
            errors.append(f'{prefix}: image missing or outside data/captured: {row["image_path"]}')
            continue
        try:
            with Image.open(candidate) as raw:
                image = ImageOps.exif_transpose(raw)
                image.load()
                width, height = image.size
                if width < 64 or height < 64:
                    errors.append(f'{prefix}: image is smaller than 64 px on one side')
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            errors.append(f'{prefix}: image cannot be decoded: {exc}')
            continue
        digest = file_hash(candidate)
        image_hashes[digest].append((split, row['verified_drug_id'], row['sample_id']))
        sessions[row['capture_session_id']].add(split)
        instances[row['pill_instance_id']].add(split)
        instance_drugs[row['pill_instance_id']].add(row['verified_drug_id'])
        split_counts[split] += 1
        known_counts[(split, row['verified_drug_id'])] += 1
        view_counts[row['view']] += 1
        condition_counts[row['condition']] += 1
        camera_counts[(row['camera_id'], row['lighting_id'])] += 1
        if row['verified_drug_id'] not in known_ids and split != 'unassigned':
            unknown_ids[row['verified_drug_id']].add(split)
    for session, values in sessions.items():
        if len(values) > 1:
            errors.append(f'capture_session_id {session} crosses splits: {sorted(values)}')
    for instance, values in instances.items():
        if len(values) > 1:
            errors.append(f'pill_instance_id {instance} crosses splits: {sorted(values)}')
        if len(instance_drugs[instance]) > 1:
            errors.append(f'pill_instance_id {instance} has conflicting drug IDs: {sorted(instance_drugs[instance])}')
    for digest, values in image_hashes.items():
        labels = {(split, drug) for split, drug, _ in values}
        if len(values) > 1 and len(labels) > 1:
            errors.append(f'image SHA-256 {digest[:12]} reused with different split/drug labels')
        elif len(values) > 1:
            warnings.append(f'image SHA-256 {digest[:12]} appears {len(values)} times in one split/drug')
    for drug, values in unknown_ids.items():
        if len(values) > 1:
            errors.append(f'unknown verified_drug_id {drug} crosses splits: {sorted(values)}')
    if split_counts['unassigned']:
        warnings.append(f'{split_counts["unassigned"]} images are unassigned and must not enter evaluation')
    for split in ('train', 'validation', 'test'):
        if not split_counts[split]:
            warnings.append(f'no images in {split}')
    return {'status': 'passed' if not errors else 'failed',
            'image_count': len(rows), 'valid_image_count': sum(split_counts.values()),
            'known_drug_ids': sorted(known_ids),
            'split_counts': dict(sorted(split_counts.items())),
            'per_drug_split_counts': {f'{split}/{drug}': count
                for (split, drug), count in sorted(known_counts.items())},
            'view_counts': dict(sorted(view_counts.items())),
            'condition_counts': dict(sorted(condition_counts.items())),
            'camera_lighting_counts': {f'{camera}/{light}': count
                for (camera, light), count in sorted(camera_counts.items())},
            'unknown_drug_id_count': len(unknown_ids),
            'errors': errors, 'warnings': warnings}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path,
                        default=ROOT / 'data/captured/manifest.csv')
    parser.add_argument('--known-config', type=Path,
                        default=ROOT / 'model/configs/recognition/camera-known-drugs.json')
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'model/reports/camera-data-audit.json')
    args = parser.parse_args()
    known_ids = read_known(args.known_config)
    report = audit(args.manifest, known_ids)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
