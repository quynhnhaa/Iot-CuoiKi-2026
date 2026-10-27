"""Train target-specific hard-negative verification heads on VAIPE using CPU.

107 is an out-of-prescription context label and is excluded. Unknown training
IDs are disjoint from every unknown validation ID. Calibration and evaluation
unknown IDs are disjoint. No test images, GPU, or camera data are used.
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from scipy.special import expit, softmax
import torch
import torch.nn.functional as F

import train_recognition_verifier as base
from benchmark_recognition_open_set import CLASSES, temperature
from evaluate_recognition_unseen_ids import load, subset, unknown_id_split
from evaluate_vaipe_target_gate_cpu import choose_target_threshold

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ROOT / 'model/runs/recognition/open_set_features_20261026'
OUT = ROOT / 'model/runs/recognition/vaipe_target_logistic_cpu_20261027'
CONTEXT_LABEL = 107


def unit(features):
    x = features.astype(np.float64)
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(min=1e-9)


def paired_scores(data, coefficients, intercepts, calibrated_temperature):
    x = unit(data['features'])
    verification = expit(x @ coefficients.T + intercepts)
    classifier = softmax(data['logits'].astype(np.float64) / calibrated_temperature, axis=1)
    return classifier * verification, classifier.argmax(1)


def evaluate_target(known, unknown, known_signal, unknown_signal, known_cal_mask,
                    unknown_cal_mask, target_index):
    kscore, kpred = known_signal[0][:, target_index], known_signal[1]
    uscore, upred = unknown_signal[0][:, target_index], unknown_signal[1]
    truth = np.array([CLASSES.index(int(value)) for value in known['class_ids']])
    threshold = choose_target_threshold(kscore[known_cal_mask], kpred[known_cal_mask],
        truth[known_cal_mask], uscore[unknown_cal_mask], upred[unknown_cal_mask],
        target_index, 0)
    def part(kmask, umask):
        positive = truth[kmask] == target_index
        accepted = (kpred[kmask] == target_index) & (kscore[kmask] >= threshold)
        false_unknown = (upred[umask] == target_index) & (uscore[umask] >= threshold)
        return {'correct_accepted': int((positive & accepted).sum()),
            'known_target_count': int(positive.sum()),
            'other_known_accepted': int((~positive & accepted).sum()),
            'other_known_count': int((~positive).sum()),
            'unknown_accepted': int(false_unknown.sum()),
            'unknown_count': int(umask.sum())}
    return {'threshold': float(threshold),
        'calibration': part(known_cal_mask, unknown_cal_mask),
        'unseen_ids': part(~known_cal_mask, ~unknown_cal_mask)}


def main():
    torch.set_num_threads(4)
    torch.manual_seed(20261027)
    kt, ut, kv, uv = (load(FEATURES, name) for name in
        ('train-known', 'train-unknown', 'validation-known', 'validation-unknown'))
    uv = subset(uv, uv['class_ids'] != CONTEXT_LABEL)
    validation_ids = set(map(int, uv['class_ids']))
    train_negative_ids = sorted(set(map(int, ut['class_ids'])) - validation_ids - {CONTEXT_LABEL})
    ut = subset(ut, np.isin(ut['class_ids'], train_negative_ids))
    if len(ut['class_ids']) < 100 or set(map(int, ut['class_ids'])) & validation_ids:
        raise ValueError('Invalid class-disjoint negative train set')
    km = base.grouped_mask('validation', 'known', 0)
    um, id_groups, counts = unknown_id_split(uv['class_ids'])
    if len(km) != len(kv['class_ids']) or len(um) != len(uv['class_ids']):
        raise ValueError('Split and features do not align')
    xk, xu = unit(kt['features']), unit(ut['features'])
    train_x = np.concatenate([xk, xu])
    train_classes = np.concatenate([kt['class_ids'], ut['class_ids']])
    target_labels = []
    target_weights = []
    fit_details = {}
    for index, class_id in enumerate(CLASSES):
        labels = (train_classes == class_id).astype(np.int64)
        positive = labels == 1
        centroid = unit(xk[kt['class_ids'] == class_id].mean(axis=0, keepdims=True))[0]
        similarity = train_x @ centroid
        negative_similarity = similarity[~positive]
        low, high = np.quantile(negative_similarity, [0.1, 0.9])
        hardness = np.clip((negative_similarity - low) / max(high-low, 1e-8), 0, 1)
        weights = np.empty(len(labels), dtype=np.float64)
        weights[positive] = .5 / positive.sum()
        negative_weight = 1 + 3*hardness
        weights[~positive] = .5*negative_weight/negative_weight.sum()
        weights *= len(labels)
        target_labels.append(labels)
        target_weights.append(weights)
        fit_details[str(class_id)] = {'positive_train': int(positive.sum()),
            'negative_train': int((~positive).sum()),
            'negative_hardness_weight': '1 + 3 * clipped train-only cosine percentile'}
    x = torch.as_tensor(train_x, dtype=torch.float32)
    y = torch.as_tensor(np.stack(target_labels, axis=1), dtype=torch.float32)
    w = torch.as_tensor(np.stack(target_weights, axis=1), dtype=torch.float32)
    model = torch.nn.Linear(x.shape[1], len(CLASSES))
    optimizer = torch.optim.AdamW(model.parameters(), lr=.01, weight_decay=.001)
    for epoch in range(200):
        logits = model(x)
        loss = (F.binary_cross_entropy_with_logits(logits, y, reduction='none') * w).mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward(); optimizer.step()
        if (epoch + 1) % 50 == 0:
            print('epoch', epoch + 1, 'loss', float(loss.detach()), flush=True)
    coefficients = model.weight.detach().numpy().astype(np.float64)
    intercepts = model.bias.detach().numpy().astype(np.float64)
    temp = temperature(kv['logits'][km], kv['class_ids'][km])
    known_signal = paired_scores(kv, coefficients, intercepts, temp)
    unknown_signal = paired_scores(uv, coefficients, intercepts, temp)
    per_target = {str(class_id): evaluate_target(kv, uv, known_signal, unknown_signal,
        km, um, index) for index, class_id in enumerate(CLASSES)}
    OUT.mkdir(parents=True, exist_ok=True)
    temp_path = OUT / 'heads.tmp'
    with temp_path.open('wb') as handle:
        np.savez_compressed(handle, coefficients=coefficients, intercepts=intercepts)
    os.replace(temp_path, OUT / 'heads.npz')
    result = {'method': 'seven target-specific hard-negative logistic heads',
        'training': {'epochs': 200, 'optimizer': 'AdamW', 'learning_rate': .01,
            'weight_decay': .001, 'seed': 20261027},
        'classes': CLASSES, 'excluded_context_label': CONTEXT_LABEL,
        'negative_train_ids': train_negative_ids,
        'negative_train_count': len(ut['class_ids']),
        'train_feature_sha256': hashlib.sha256(train_x.tobytes()).hexdigest(),
        'temperature': float(temp), 'fit': fit_details,
        'unknown_calibration_ids': id_groups[0],
        'unknown_evaluation_ids': id_groups[1],
        'unknown_counts': counts, 'per_target': per_target,
        'test_used': False, 'device': 'cpu',
        'validation_previously_inspected': True}
    (OUT / 'validation-results.json').write_text(json.dumps(result, indent=2) + '\n')
    for class_id in CLASSES:
        row = per_target[str(class_id)]['unseen_ids']
        print(class_id, row['correct_accepted'], '/', row['known_target_count'],
            'false unknown', row['unknown_accepted'], '/', row['unknown_count'], flush=True)


if __name__ == '__main__':
    main()
