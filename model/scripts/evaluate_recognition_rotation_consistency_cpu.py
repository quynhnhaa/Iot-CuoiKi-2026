"""Conservative target-aware view-consistency gate on previously inspected VAIPE validation.

Primary predeclared policy: original target gate AND PIM prediction agrees at
90 and 180 degrees. Secondary 180-only policy is reported as an ablation.
No training, threshold search, VAIPE test or GPU use. Never enables actuation.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'model/scripts'))
from train_recognition_pim import CLASSES, build_model  # noqa: E402
from train_recognition_verifier import Verifier  # noqa: E402

RUNS = ROOT / 'model/runs/recognition'
FEATURES = RUNS / 'open_set_features_20261026'
KNOWN = ROOT / 'data/processed/vaipe/recognition/yolov7_rois/validation.csv'
UNKNOWN = ROOT / 'data/processed/vaipe/recognition/yolov7_unknown/validation.csv'
PIM = RUNS / 'pim_resnet50_7class_20261026_v2/best.pt'
VERIFIER = RUNS / 'class_conditioned_verifier_20261027/best.pt'
GATES = RUNS / 'vaipe_target_gate_cpu_20261027/results.json'
OUT = RUNS / 'rotation_consistency_cpu_20261027'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_checkpoint(path):
    from numpy._core.multiarray import _reconstruct
    allowed = [_reconstruct, np.ndarray, np.dtype,
               type(np.dtype('uint32')), type(np.dtype('float32')), type(np.dtype('float64'))]
    unsafe = set(torch.serialization.get_unsafe_globals_in_checkpoint(path))
    expected = {'numpy._core.multiarray._reconstruct', 'numpy.dtype', 'numpy.ndarray'}
    if not unsafe.issubset(expected):
        raise ValueError(f'unexpected checkpoint globals: {sorted(unsafe - expected)}')
    with torch.serialization.safe_globals(allowed):
        return torch.load(path, map_location='cpu', weights_only=True)


def read_data(kind):
    manifest = KNOWN if kind == 'known' else UNKNOWN
    with manifest.open(newline='') as f:
        rows = list(csv.DictReader(f))
    with np.load(FEATURES / f'validation-{kind}.npz') as data:
        features = {name: data[name].copy() for name in data.files}
    if len(rows) != len(features['class_ids']):
        raise ValueError(f'{kind}: feature/manifest length mismatch')
    for row, image_id, annotation, class_id in zip(rows, features['image_ids'],
                                                     features['annotation_indices'], features['class_ids']):
        if row['image_id'] != image_id or int(row['annotation_index']) != annotation or int(row['class_id']) != class_id:
            raise ValueError(f'{kind}: feature/manifest row mismatch')
    if kind == 'unknown':
        keep = features['class_ids'] != 107
        rows = [r for r, flag in zip(rows, keep) if flag]
        features = {key: value[keep] for key, value in features.items()}
    return rows, features


def split_masks(rows, features, gate_result, kind):
    if kind == 'known':
        calibration = np.array([int(hashlib.sha256(r['group_id'].encode()).hexdigest(), 16) % 2 == 0
                                for r in rows], dtype=bool)
    else:
        ids = set(gate_result['unknown_calibration_ids'])
        evaluation = set(gate_result['unknown_evaluation_ids'])
        if ids & evaluation:
            raise ValueError('unknown calibration/evaluation IDs overlap')
        if set(map(int, features['class_ids'])) != ids | evaluation:
            raise ValueError('unknown ID partitions changed')
        calibration = np.isin(features['class_ids'], list(ids))
    return calibration, ~calibration


def original_gate(features, verifier, temperature, thresholds):
    x = torch.from_numpy(features['features']).float()
    logits = torch.from_numpy(features['logits']).float()
    with torch.inference_mode():
        classifier = (logits / temperature).softmax(1)
        prediction = classifier.argmax(1)
        verification = torch.cat([verifier(F.normalize(batch, dim=1)).sigmoid()
                                  for batch in x.split(512)], dim=0)
        score = (classifier * verification).gather(1, prediction[:, None]).squeeze(1)
    pred = prediction.numpy()
    scores = score.numpy()
    return pred, scores, scores >= thresholds[pred]


def load_crop(row, kind):
    if kind == 'known':
        with Image.open(ROOT / row['crop_path']) as image:
            return image.convert('RGB')
    with Image.open(ROOT / row['image_path']) as image:
        image = ImageOps.exif_transpose(image).convert('RGB')
        box = tuple(int(row[f'crop_{key}']) for key in ('left', 'top', 'right', 'bottom'))
        return image.crop(box)


def rotation_predictions(rows, candidate, kind, model, batch_size=8):
    transform = transforms.Compose([transforms.Resize((360, 360)),
                                    transforms.CenterCrop(320), transforms.ToTensor(),
                                    transforms.Normalize([.485, .456, .406], [.229, .224, .225])])
    rot90 = np.full(len(rows), -1, dtype=np.int64)
    rot180 = np.full(len(rows), -1, dtype=np.int64)
    indices = np.flatnonzero(candidate)
    for start in range(0, len(indices), batch_size):
        current = indices[start:start + batch_size]
        inputs = torch.stack([transform(load_crop(rows[i], kind)) for i in current])
        with torch.inference_mode():
            out90 = model(torch.rot90(inputs, 1, dims=(-2, -1)))['comb_outs'].argmax(1)
            out180 = model(torch.rot90(inputs, 2, dims=(-2, -1)))['comb_outs'].argmax(1)
        rot90[current] = out90.numpy()
        rot180[current] = out180.numpy()
        if (start // batch_size + 1) % 20 == 0 or start + batch_size >= len(indices):
            print(f'{kind}: {min(start + batch_size, len(indices))}/{len(indices)} candidates', flush=True)
    return rot90, rot180


def summarize(kind, features, predicted, accepted, rotated90, rotated180, calibration):
    truth = features['class_ids']
    result = {}
    for split, mask in (('calibration', calibration), ('unseen_or_group_holdout', ~calibration)):
        per_target = {}
        for index, class_id in enumerate(CLASSES):
            if kind == 'known':
                positive = mask & (truth == class_id)
                wrong = mask & (truth != class_id)
            else:
                positive = np.zeros(len(mask), dtype=bool)
                wrong = mask
            baseline = accepted & (predicted == index)
            policies = {'baseline': baseline,
                        'rotation_180': baseline & (rotated180 == index),
                        'rotation_90_180': baseline & (rotated90 == index) & (rotated180 == index)}
            per_target[str(class_id)] = {name: {'target_accepted': int((positive & decision).sum()),
                                                'target_total': int(positive.sum()),
                                                'other_accepted': int((wrong & decision).sum()),
                                                'other_total': int(wrong.sum())}
                                         for name, decision in policies.items()}
        result[split] = per_target
    return result


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    torch.set_num_threads(8)
    gates = json.loads(GATES.read_text())
    if gates['test_used'] or not gates['validation_previously_inspected']:
        raise ValueError('unexpected gate provenance')
    base = gates['models']['original']
    thresholds = np.array([base['target_zero_calibration_unknown']['per_target'][str(c)]['threshold']
                           for c in CLASSES])
    pim_ckpt = safe_checkpoint(PIM)
    model = build_model(pim_ckpt['config'], load_imagenet=False)
    model.load_state_dict(pim_ckpt['model'])
    model.eval()
    verifier_ckpt = safe_checkpoint(VERIFIER)
    verifier = Verifier()
    verifier.load_state_dict(verifier_ckpt['model'])
    verifier.eval()
    payload = {'status': 'research_only', 'device': 'cpu', 'primary_policy': 'baseline AND 90/180 degree top-ID agreement',
               'secondary_policy': 'baseline AND 180 degree top-ID agreement',
               'test_used': False, 'validation_previously_inspected': True,
               'class_107_excluded': True, 'thresholds_unchanged': True,
               'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in
                                 (KNOWN, UNKNOWN, PIM, VERIFIER, GATES,
                                  FEATURES / 'validation-known.npz', FEATURES / 'validation-unknown.npz')},
               'kinds': {}}
    output_rows = []
    for kind in ('known', 'unknown'):
        rows, features = read_data(kind)
        calibration, evaluation = split_masks(rows, features, gates, kind)
        predicted, scores, accepted = original_gate(features, verifier, base['temperature'], thresholds)
        if len(rows) != (1943 if kind == 'known' else 2828) or int(calibration.sum()) != (1216 if kind == 'known' else 1414):
            raise ValueError(f'{kind}: expected split counts changed')
        rot90, rot180 = rotation_predictions(rows, accepted, kind, model)
        payload['kinds'][kind] = {'candidate_count': int(accepted.sum()),
                                  'evaluation_count': int(evaluation.sum()),
                                  'metrics': summarize(kind, features, predicted, accepted, rot90, rot180, calibration)}
        for i in np.flatnonzero(accepted):
            output_rows.append({'kind': kind, 'split': 'calibration' if calibration[i] else 'unseen_or_group_holdout',
                                'image_id': rows[i]['image_id'], 'annotation_index': rows[i]['annotation_index'],
                                'true_id': int(features['class_ids'][i]), 'predicted_id': int(CLASSES[predicted[i]]),
                                'baseline_score': float(scores[i]), 'threshold': float(thresholds[predicted[i]]),
                                'rot90_predicted_id': int(CLASSES[rot90[i]]),
                                'rot180_predicted_id': int(CLASSES[rot180[i]])})
    OUT.mkdir(parents=True)
    (OUT / 'results.json').write_text(json.dumps(payload, indent=2) + '\n')
    with (OUT / 'candidates.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(output_rows[0]))
        writer.writeheader(); writer.writerows(output_rows)
    print(json.dumps({'candidate_counts': {k: v['candidate_count'] for k, v in payload['kinds'].items()},
                      'results': {k: v['metrics']['unseen_or_group_holdout'] for k, v in payload['kinds'].items()}},
                     indent=2), flush=True)


if __name__ == '__main__':
    main()
