"""Explore a second-order local-feature agreement gate for VAIPE recognition.

Gallery: 48 distinct train photo groups per known ID. Candidate queries are
exactly the baseline-accepted validation ROIs from the locked rotation audit.
No model training, VAIPE test access, threshold tuning or GPU. Research only.
"""
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'model/scripts'))
from train_recognition_pim import CLASSES, build_model  # noqa: E402

PIM = ROOT / 'model/runs/recognition/pim_resnet50_7class_20261026_v2/best.pt'
TRAIN = ROOT / 'data/processed/vaipe/recognition/yolov7_rois/train.csv'
KNOWN = ROOT / 'data/processed/vaipe/recognition/yolov7_rois/validation.csv'
UNKNOWN = ROOT / 'data/processed/vaipe/recognition/yolov7_unknown/validation.csv'
CANDIDATES = ROOT / 'model/runs/recognition/rotation_consistency_cpu_20261027/candidates.csv'
OUT = ROOT / 'model/runs/recognition/bilinear_local_cpu_20261027'
SEED = 20261027
GALLERY_PER_CLASS = 48
DIM = 64


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def rows(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def gallery_rows():
    source = rows(TRAIN)
    selected = []
    for cls in CLASSES:
        entries = sorted((r for r in source if int(r['class_id']) == cls),
                         key=lambda r: hashlib.sha256(f"{SEED}:{r['group_id']}:{r['image_id']}:{r['annotation_index']}".encode()).hexdigest())
        seen = set()
        for row in entries:
            if row['group_id'] not in seen:
                selected.append(row)
                seen.add(row['group_id'])
            if len(seen) == GALLERY_PER_CLASS:
                break
        if len(seen) != GALLERY_PER_CLASS:
            raise ValueError(f'class {cls} has fewer than {GALLERY_PER_CLASS} groups')
    return selected


def query_rows():
    with CANDIDATES.open(newline='') as f:
        candidates = list(csv.DictReader(f))
    lookup = {}
    for kind, path in (('known', KNOWN), ('unknown', UNKNOWN)):
        for row in rows(path):
            key = kind, row['image_id'], row['annotation_index']
            if key in lookup:
                raise ValueError(f'duplicate ROI key: {key}')
            lookup[key] = row
    result = []
    for candidate in candidates:
        key = candidate['kind'], candidate['image_id'], candidate['annotation_index']
        row = lookup[key]
        if int(row['class_id']) != int(candidate['true_id']):
            raise ValueError('candidate class differs from manifest')
        if int(row['class_id']) == 107:
            raise ValueError('class 107 cannot be appearance unknown')
        result.append((candidate, row))
    if len(result) != 927:
        raise ValueError(f'candidate count changed: {len(result)}')
    return result


def crop(row, kind):
    if kind != 'unknown':
        with Image.open(ROOT / row['crop_path']) as image:
            return image.convert('RGB')
    with Image.open(ROOT / row['image_path']) as image:
        image = ImageOps.exif_transpose(image).convert('RGB')
        box = tuple(int(row[f'crop_{part}']) for part in ('left', 'top', 'right', 'bottom'))
        return image.crop(box)


def safe_pim():
    from numpy._core.multiarray import _reconstruct
    allowed = [_reconstruct, np.ndarray, np.dtype,
               type(np.dtype('uint32')), type(np.dtype('float32')), type(np.dtype('float64'))]
    expected = {'numpy._core.multiarray._reconstruct', 'numpy.dtype', 'numpy.ndarray'}
    if not set(torch.serialization.get_unsafe_globals_in_checkpoint(PIM)).issubset(expected):
        raise ValueError('unexpected checkpoint globals')
    with torch.serialization.safe_globals(allowed):
        saved = torch.load(PIM, map_location='cpu', weights_only=True)
    model = build_model(saved['config'], load_imagenet=False)
    model.load_state_dict(saved['model'])
    model.eval()
    return model


def second_order_map(feature_map, projection):
    batch, channels, height, width = feature_map.shape
    x = feature_map.flatten(2).transpose(1, 2)
    x = x - x.mean(1, keepdim=True)
    projected = x @ projection
    covariance = projected.transpose(1, 2) @ projected / max(1, height * width - 1)
    triangle = torch.triu_indices(DIM, DIM)
    return F.normalize(covariance[:, triangle[0], triangle[1]], dim=1).cpu().numpy()


def extract(model, entries, projection, label, batch_size=8):
    norm = transforms.Normalize([.485, .456, .406], [.229, .224, .225])
    transform = transforms.Compose([transforms.Resize((360, 360)),
                                    transforms.CenterCrop(320), transforms.ToTensor(), norm])
    result = []
    for start in range(0, len(entries), batch_size):
        batch = entries[start:start + batch_size]
        images = torch.stack([transform(crop(row, kind)) for kind, row in batch])
        with torch.inference_mode():
            layer4 = model.backbone(images)['layer4']
            result.append(second_order_map(layer4, projection))
        if (start // batch_size + 1) % 15 == 0 or start + batch_size >= len(entries):
            print(f'{label}: {min(start + batch_size, len(entries))}/{len(entries)}', flush=True)
    return np.concatenate(result)


def summary(candidates, class_prediction):
    records = {}
    for split in ('calibration', 'unseen_or_group_holdout'):
        per_class = {}
        for cls in CLASSES:
            subset = [i for i, (candidate, _) in enumerate(candidates)
                      if candidate['split'] == split and int(candidate['predicted_id']) == cls]
            known = [i for i in subset if candidates[i][0]['kind'] == 'known' and
                     int(candidates[i][0]['true_id']) == cls]
            other_known = [i for i in subset if candidates[i][0]['kind'] == 'known' and
                           int(candidates[i][0]['true_id']) != cls]
            unknown = [i for i in subset if candidates[i][0]['kind'] == 'unknown']
            per_class[str(cls)] = {'baseline_known_accepted': len(known),
                                   'candidate_known_accepted': int(sum(class_prediction[i] == cls for i in known)),
                                   'baseline_other_known_accepted': len(other_known),
                                   'candidate_other_known_accepted': int(sum(class_prediction[i] == cls for i in other_known)),
                                   'baseline_unknown_accepted': len(unknown),
                                   'candidate_unknown_accepted': int(sum(class_prediction[i] == cls for i in unknown))}
        records[split] = per_class
    return records


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    torch.set_num_threads(8)
    gallery = gallery_rows()
    candidates = query_rows()
    model = safe_pim()
    generator = torch.Generator().manual_seed(SEED)
    projection = torch.randn(2048, DIM, generator=generator) / np.sqrt(2048)
    gallery_features = extract(model, [('known', row) for row in gallery], projection, 'gallery')
    query_features = extract(model, [(candidate['kind'], row) for candidate, row in candidates], projection, 'query')
    prototypes = []
    for cls in CLASSES:
        mask = np.array([int(row['class_id']) == cls for row in gallery])
        mean = gallery_features[mask].mean(axis=0)
        prototypes.append(mean / max(np.linalg.norm(mean), 1e-6))
    centroid_score = query_features @ np.stack(prototypes).T
    centroid_pred = np.asarray(CLASSES)[centroid_score.argmax(1)]
    max_scores = np.stack([(query_features @ gallery_features[np.array([int(r['class_id']) == cls for r in gallery])].T).max(1)
                           for cls in CLASSES], axis=1)
    max_pred = np.asarray(CLASSES)[max_scores.argmax(1)]
    payload = {'status': 'research_only', 'device': 'cpu', 'test_used': False,
               'validation_previously_inspected': True, 'class_107_excluded': True,
               'gallery_per_class': GALLERY_PER_CLASS, 'gallery_group_distinct': True,
               'feature': f'centered layer4 covariance after fixed {DIM}-D random projection, upper triangle cosine',
               'primary_policy': 'original target gate AND nearest covariance centroid class agrees',
               'ablation_policy': 'original target gate AND nearest individual gallery class agrees',
               'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in (PIM, TRAIN, KNOWN, UNKNOWN, CANDIDATES)},
               'gallery_count': len(gallery), 'candidate_count': len(candidates),
               'centroid': summary(candidates, centroid_pred), 'nearest_gallery': summary(candidates, max_pred)}
    OUT.mkdir(parents=True)
    (OUT / 'results.json').write_text(json.dumps(payload, indent=2) + '\n')
    with (OUT / 'candidate-scores.csv').open('w', newline='') as f:
        fields = ['kind', 'split', 'image_id', 'annotation_index', 'true_id', 'predicted_id',
                  'centroid_predicted_id', 'centroid_target_similarity', 'nearest_gallery_predicted_id',
                  'nearest_gallery_target_similarity']
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i, (candidate, _) in enumerate(candidates):
            cls_index = CLASSES.index(int(candidate['predicted_id']))
            writer.writerow({**{key: candidate[key] for key in fields[:6]},
                             'centroid_predicted_id': int(centroid_pred[i]),
                             'centroid_target_similarity': float(centroid_score[i, cls_index]),
                             'nearest_gallery_predicted_id': int(max_pred[i]),
                             'nearest_gallery_target_similarity': float(max_scores[i, cls_index])})
    print(json.dumps({'centroid_eval': payload['centroid']['unseen_or_group_holdout'],
                      'nearest_eval': payload['nearest_gallery']['unseen_or_group_holdout']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
