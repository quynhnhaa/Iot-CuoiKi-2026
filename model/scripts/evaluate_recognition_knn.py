"""Evaluate frozen-feature nearest-neighbor open-set scores without reading test.

All candidate definitions are fixed in code. Choose a score/threshold on group
calibration, then report the previously inspected validation remainder as an
exploratory diagnostic rather than an independent test.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from benchmark_recognition_open_set import CLASSES, normalized_features, temperature
from train_recognition_verifier import grouped_mask

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ROOT / 'model/runs/recognition/open_set_features_20261026'
OUT = ROOT / 'model/runs/recognition/knn_open_set_20261027'


def load(name):
    with np.load(FEATURES / f'{name}.npz') as handle:
        return {key: handle[key].copy() for key in handle.files}


def neighbor_scores(train, data, device, k=5):
    gallery = normalized_features(train).to(device)
    gallery_labels = torch.as_tensor(train['class_ids'], device=device)
    result = []
    with torch.inference_mode():
        for batch in normalized_features(data).split(256):
            similarity = batch.to(device) @ gallery.T
            result.append(torch.stack([
                similarity[:, gallery_labels == cls].topk(k, dim=1).values.mean(1)
                for cls in CLASSES], dim=1).cpu())
    return torch.cat(result).numpy()


def summarize(data, score, pred, mask, threshold, unknown=False):
    accepted = score[mask] >= threshold
    if unknown:
        return {'count': int(mask.sum()), 'false_accepted': int(accepted.sum()),
                'false_accept_rate': float(accepted.mean())}
    truth = np.array([CLASSES.index(int(v)) for v in data['class_ids'][mask]])
    prediction = pred[mask]
    per_class = {str(cls): {'correct_accepted': int(((truth == index) &
        (prediction == truth) & accepted).sum()), 'total': int((truth == index).sum())}
        for index, cls in enumerate(CLASSES)}
    return {'count': int(mask.sum()), 'correct_accept_rate': float(np.mean(accepted &
            (prediction == truth))), 'wrong_accept_count': int((accepted &
            (prediction != truth)).sum()), 'per_class': per_class}


def threshold_at_far(known_score, known_correct, unknown_score, target=.01):
    # Strictly choose an operating point with <= target calibration FAR.
    candidates = np.unique(np.r_[known_score, unknown_score, np.nextafter(max(
        np.max(known_score), np.max(unknown_score)), np.inf)])
    eligible = candidates[(unknown_score[:, None] >= candidates).mean(0) <= target]
    if not len(eligible):
        raise ValueError('No eligible threshold')
    true_accept = ((known_score[:, None] >= eligible) & known_correct[:, None]).mean(0)
    far = (unknown_score[:, None] >= eligible).mean(0)
    best = np.lexsort((-eligible, far, -true_accept))[0]
    return float(eligible[best])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    args = parser.parse_args()
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable')
    train, known, unknown = (load(name) for name in ('train-known',
        'validation-known', 'validation-unknown'))
    device = torch.device(args.device)
    known_neighbor = neighbor_scores(train, known, device)
    unknown_neighbor = neighbor_scores(train, unknown, device)
    km, um = grouped_mask('validation', 'known', 0), grouped_mask('validation', 'unknown', 0)
    if len(km) != len(known['class_ids']) or len(um) != len(unknown['class_ids']):
        raise ValueError('Manifest and features mismatch')
    temp = temperature(known['logits'][km], known['class_ids'][km])
    known_prob = F.softmax(torch.tensor(known['logits']) / temp, dim=1).numpy()
    unknown_prob = F.softmax(torch.tensor(unknown['logits']) / temp, dim=1).numpy()
    kp, up = known_prob.argmax(1), unknown_prob.argmax(1)
    true = np.array([CLASSES.index(int(v)) for v in known['class_ids']])
    def signals(neighbor, prob, pred, method):
        row = np.arange(len(pred))
        own = neighbor[row, pred]
        other = np.partition(np.where(np.arange(len(CLASSES))[None, :] == pred[:, None],
            -np.inf, neighbor), -1, axis=1)[:, -1]
        if method == 'own':
            return own
        if method == 'margin':
            return own - other
        if method == 'joint':
            return own * prob[row, pred]
        raise ValueError(method)
    results = {}
    for method in ('own', 'margin', 'joint'):
        ks = signals(known_neighbor, known_prob, kp, method)
        us = signals(unknown_neighbor, unknown_prob, up, method)
        threshold = threshold_at_far(ks[km], kp[km] == true[km], us[um])
        results[method] = {'threshold': threshold,
            'calibration_known': summarize(known, ks, kp, km, threshold),
            'calibration_unknown': summarize(unknown, us, up, um, threshold, True),
            'remainder_known': summarize(known, ks, kp, ~km, threshold),
            'remainder_unknown': summarize(unknown, us, up, ~um, threshold, True)}
    selected = max(results, key=lambda name: (results[name]['calibration_known']
        ['correct_accept_rate'], -results[name]['calibration_known']['wrong_accept_count'],
        -results[name]['calibration_unknown']['false_accept_rate']))
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'methods': results, 'selected_on_calibration': selected,
        'gallery_count': len(train['class_ids']), 'temperature': temp,
        'test_used': False, 'remainder_is_exploratory': True, 'device': args.device,
        'gallery_sha256': hashlib.sha256(train['features'].tobytes()).hexdigest()}
    (OUT / 'validation-results.json').write_text(json.dumps(report, indent=2) + '\n')
    for method, item in results.items():
        print(method, 'cal', item['calibration_known']['correct_accept_rate'],
              item['calibration_unknown']['false_accepted'], 'rem',
              item['remainder_known']['correct_accept_rate'],
              item['remainder_unknown']['false_accepted'], flush=True)
    print('selected:', selected, flush=True)


if __name__ == '__main__':
    main()
