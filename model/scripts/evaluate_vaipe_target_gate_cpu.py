"""Correct VAIPE class-107 semantics and evaluate target-aware CPU gates.

107 is out-of-prescription context, not a verified novel pill identity. Exclude
it from appearance-based unknown metrics. No training, GPU, or test access.
"""
import json
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

import train_recognition_verifier as gate
from benchmark_recognition_open_set import CLASSES, normalized_features, temperature
from evaluate_recognition_unseen_ids import load, subset, unknown_id_split

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / 'model/runs/recognition'
OUT = RUNS / 'vaipe_target_gate_cpu_20261027'
CLASS_CONTEXT_ONLY = 107


def score_matrices(run_name, feature_dir, km):
    known = load(feature_dir, 'validation-known')
    unknown_all = load(feature_dir, 'validation-unknown')
    keep = unknown_all['class_ids'] != CLASS_CONTEXT_ONLY
    unknown = subset(unknown_all, keep)
    saved = torch.load(RUNS / run_name / 'best.pt', map_location='cpu', weights_only=False)
    model = gate.Verifier(known['features'].shape[1])
    model.load_state_dict(saved['model']); model.eval()
    temp = temperature(known['logits'][km], known['class_ids'][km])

    def one(data):
        with torch.inference_mode():
            verify = torch.cat([model(batch).sigmoid() for batch in
                normalized_features(data).split(1024)]).numpy()
        classifier = F.softmax(torch.as_tensor(data['logits'], dtype=torch.float32)/temp,
                               dim=1).numpy()
        return classifier * verify, classifier.argmax(1)
    return known, unknown, one(known), one(unknown), float(temp)


def global_result(known, unknown, ks, us, km, um):
    k_matrix, kp = ks
    u_matrix, up = us
    kr = np.arange(len(kp)); ur = np.arange(len(up))
    kscore, uscore = k_matrix[kr, kp], u_matrix[ur, up]
    gate.CALIBRATION_KNOWN = subset(known, km)
    threshold = gate.select_threshold((kscore[km], kp[km]), (uscore[um], up[um]))
    return {'threshold': float(threshold),
        'calibration': gate.summarize(subset(known, km), subset(unknown, um),
            (kscore[km], kp[km]), (uscore[um], up[um]), threshold),
        'unseen_ids': gate.summarize(subset(known, ~km), subset(unknown, ~um),
            (kscore[~km], kp[~km]), (uscore[~um], up[~um]), threshold)}


def choose_target_threshold(score, pred, truth, unknown_score, unknown_pred,
                            target, unknown_budget):
    pos = (truth == target) & (pred == target)
    wrong_known = (truth != target) & (pred == target)
    unknown_predicted = unknown_pred == target
    candidates = np.unique(np.r_[score[pos], score[wrong_known],
        unknown_score[unknown_predicted]])
    candidates = np.r_[math.inf, candidates[::-1]]
    best = None
    for threshold in candidates:
        wrong_count = int((score[wrong_known] >= threshold).sum())
        unknown_count = int((unknown_score[unknown_predicted] >= threshold).sum())
        if wrong_count != 0 or unknown_count > unknown_budget:
            continue
        positive_count = int((score[pos] >= threshold).sum())
        key = (positive_count, -unknown_count, threshold)
        if best is None or key > best[0]:
            best = (key, float(threshold))
    return best[1]


def target_result(known, unknown, ks, us, km, um, far):
    k_matrix, kp = ks
    u_matrix, up = us
    truth = np.array([CLASSES.index(int(value)) for value in known['class_ids']])
    budget = math.floor(far * int(um.sum()))
    results = {}
    for index, class_id in enumerate(CLASSES):
        threshold = choose_target_threshold(k_matrix[km, index], kp[km], truth[km],
            u_matrix[um, index], up[um], index, budget)
        def part(kmask, umask):
            positive = (truth[kmask] == index)
            pred = kp[kmask]
            accepted = (pred == index) & (k_matrix[kmask, index] >= threshold)
            bad_unknown = (up[umask] == index) & \
                (u_matrix[umask, index] >= threshold)
            return {'known_target_accepted': int((positive & accepted).sum()),
                'known_target_total': int(positive.sum()),
                'other_known_accepted': int((~positive & accepted).sum()),
                'other_known_total': int((~positive).sum()),
                'unknown_accepted': int(bad_unknown.sum()),
                'unknown_total': int(umask.sum())}
        results[str(class_id)] = {'threshold': threshold,
            'calibration': part(km, um), 'unseen_ids': part(~km, ~um)}
    return {'unknown_budget_per_target_count': budget, 'per_target': results}


def main():
    torch.set_num_threads(4)
    base_known = load(RUNS / 'open_set_features_20261026', 'validation-known')
    base_unknown = load(RUNS / 'open_set_features_20261026', 'validation-unknown')
    km = gate.grouped_mask('validation', 'known', 0)
    keep = base_unknown['class_ids'] != CLASS_CONTEXT_ONLY
    clean_unknown = subset(base_unknown, keep)
    um, ids, counts = unknown_id_split(clean_unknown['class_ids'])
    if not set(ids[0]).isdisjoint(ids[1]) or CLASS_CONTEXT_ONLY in ids[0]+ids[1]:
        raise ValueError('Unknown ID split is invalid')
    records = {}
    for name, run_name, feature_dir in [
        ('original', 'class_conditioned_verifier_20261027',
         RUNS / 'open_set_features_20261026'),
        ('spatial', 'class_conditioned_verifier_spatial_20261027',
         RUNS / 'pim_spatial_features_20261027')]:
        known, unknown, ks, us, temp = score_matrices(run_name, feature_dir, km)
        for source, current in [(base_known, known), (clean_unknown, unknown)]:
            for key in ('class_ids', 'image_ids', 'annotation_indices'):
                if not np.array_equal(source[key], current[key]):
                    raise ValueError(f'{name}: input rows changed: {key}')
        records[name] = {'temperature': temp,
            'global': global_result(known, unknown, ks, us, km, um),
            'target_zero_calibration_unknown': target_result(known, unknown,
                ks, us, km, um, 0.),
            'target_one_percent_calibration_unknown': target_result(known, unknown,
                ks, us, km, um, .01)}
        g = records[name]['global']['unseen_ids']
        print(name, 'global known', g['known_correct_accept_rate'],
            'unknown', g['unknown_false_accept_count'], '/', g['unknown_count'], flush=True)
        for policy in ['target_zero_calibration_unknown',
                       'target_one_percent_calibration_unknown']:
            per = records[name][policy]['per_target']
            print(name, policy, 'known', sum(x['unseen_ids']['known_target_accepted']
                for x in per.values()), 'unknown-context-false', sum(
                x['unseen_ids']['unknown_accepted'] for x in per.values()), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'results.json').write_text(json.dumps({'excluded_class_107_count':
        int((~keep).sum()), 'unknown_calibration_ids': ids[0],
        'unknown_evaluation_ids': ids[1], 'unknown_counts': counts,
        'known_calibration_count': int(km.sum()),
        'known_evaluation_count': int((~km).sum()),
        'models': records, 'test_used': False,
        'validation_previously_inspected': True,
        'device': 'cpu'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
