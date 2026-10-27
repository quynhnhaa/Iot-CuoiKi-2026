"""Allocate one calibration FAR budget across seven class thresholds.

Uses a fixed multilayer verifier chosen on calibration. The unknown evaluation
IDs are disjoint from calibration IDs. Previously inspected validation remains
exploratory; test is never read.
"""
import json
import math
from pathlib import Path

import numpy as np
import torch

import train_recognition_verifier as v
from benchmark_recognition_open_set import CLASSES, temperature
from evaluate_recognition_unseen_ids import load, unknown_id_split, subset

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / 'model/runs/recognition'
FEATURES = RUNS / 'pim_multilayer_features_20261027'
CHECKPOINT = RUNS / 'class_conditioned_verifier_multilayer_20261027/best.pt'
OUT = RUNS / 'multilayer_class_policy_20261027'


def options_for_class(score, pred, labels, unknown_score, unknown_pred, class_index, budget):
    positive = (pred == class_index) & (labels == class_index)
    wrong = (pred == class_index) & (labels != class_index)
    negative = unknown_pred == class_index
    pool = np.unique(np.r_[score[positive], score[wrong], unknown_score[negative]])
    candidates = np.r_[math.inf, pool[::-1]]
    options = {}
    for threshold in candidates:
        false_unknown = int((unknown_score[negative] >= threshold).sum())
        if false_unknown > budget:
            break
        if (score[wrong] >= threshold).any():
            continue
        gain = int((score[positive] >= threshold).sum())
        if false_unknown not in options or gain > options[false_unknown][0]:
            options[false_unknown] = (gain, float(threshold))
    return options


def optimize(known, unknown, known_signal, unknown_signal, budget):
    ks, kp = known_signal[:2]
    us, up = unknown_signal[:2]
    labels = np.array([CLASSES.index(int(value)) for value in known['class_ids']])
    totals = np.bincount(labels, minlength=len(CLASSES))
    options = [options_for_class(ks, kp, labels, us, up, index, budget)
               for index in range(len(CLASSES))]
    dp = {0: (0.0, [])}
    for index, class_options in enumerate(options):
        next_dp = {}
        for spent, (gain, selections) in dp.items():
            for cost, (accepted, threshold) in class_options.items():
                new_cost = spent + cost
                if new_cost > budget:
                    continue
                new_gain = gain + accepted / totals[index]
                if new_cost not in next_dp or new_gain > next_dp[new_cost][0]:
                    next_dp[new_cost] = (new_gain, selections + [threshold])
        dp = next_dp
    if not dp:
        raise ValueError('No feasible class policy')
    spent = max(dp, key=lambda key: (dp[key][0], -key))
    return np.array(dp[spent][1]), spent, dp[spent][0]/len(CLASSES)


def summary(data, signal, thresholds, unknown=False):
    score, pred = signal[:2]
    accepted = score >= thresholds[pred]
    if unknown:
        return {'count': len(score), 'false_accepted': int(accepted.sum()),
            'false_accept_rate': float(accepted.mean())}
    true = np.array([CLASSES.index(int(value)) for value in data['class_ids']])
    per_class = {str(cls): {'correct_accepted': int(((true == index) &
        (pred == true) & accepted).sum()), 'total': int((true == index).sum())}
        for index, cls in enumerate(CLASSES)}
    return {'count': len(score), 'correct_accepted': int(((pred == true) & accepted).sum()),
        'correct_accept_rate': float(np.mean((pred == true) & accepted)),
        'wrong_accepted': int(((pred != true) & accepted).sum()),
        'macro_coverage': float(np.mean([entry['correct_accepted']/entry['total']
            for entry in per_class.values()])), 'per_class': per_class}


def main():
    known, unknown = load(FEATURES, 'validation-known'), load(FEATURES, 'validation-unknown')
    km = v.grouped_mask('validation', 'known', 0)
    um, id_groups, counts = unknown_id_split(unknown['class_ids'])
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    checkpoint = torch.load(CHECKPOINT, map_location='cpu', weights_only=False)
    model = v.Verifier(known['features'].shape[1]).to(device)
    model.load_state_dict(checkpoint['model']); model.eval()
    temp = temperature(known['logits'][km], known['class_ids'][km])
    ks, us = v.predict(model, known, device, temp), v.predict(model, unknown, device, temp)
    ck, cu, rk, ru = subset(known, km), subset(unknown, um), \
        subset(known, ~km), subset(unknown, ~um)
    cks = tuple(x[km] for x in ks[:2]); cus = tuple(x[um] for x in us[:2])
    rks = tuple(x[~km] for x in ks[:2]); rus = tuple(x[~um] for x in us[:2])
    results = {}
    for target_far in (.005, .01):
        budget = math.floor(target_far * len(cu['class_ids']))
        thresholds, spent, macro = optimize(ck, cu, cks, cus, budget)
        results[str(target_far)] = {'budget_count': budget, 'used_count': spent,
            'thresholds_by_id': {str(cls): float(value) for cls, value in zip(CLASSES, thresholds)},
            'calibration_known': summary(ck, cks, thresholds),
            'calibration_unknown': summary(cu, cus, thresholds, True),
            'unseen_known': summary(rk, rks, thresholds),
            'unseen_unknown': summary(ru, rus, thresholds, True)}
        item = results[str(target_far)]
        print(target_far, 'cal', item['calibration_known']['correct_accept_rate'],
            item['calibration_unknown']['false_accepted'], 'unseen',
            item['unseen_known']['correct_accept_rate'],
            item['unseen_unknown']['false_accepted'], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'results.json').write_text(json.dumps({'checkpoint': str(CHECKPOINT.relative_to(ROOT)),
        'unknown_calibration_ids': id_groups[0], 'unknown_evaluation_ids': id_groups[1],
        'unknown_counts': counts, 'policies': results, 'test_used': False,
        'previously_inspected_validation': True}, indent=2) + '\n')


if __name__ == '__main__':
    main()
