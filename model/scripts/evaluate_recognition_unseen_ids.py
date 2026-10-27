"""Compare predeclared recognizers with class-disjoint unknown calibration/evaluation.

Unknown validation IDs are assigned to two count-balanced sets using labels
and counts only, never model scores. Known images retain group-hashed split.
Old validation has been inspected before, so results remain exploratory.
"""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import torch

import train_recognition_verifier as verifier
from train_recognition_unknown_head import UnknownHead, signals as unknown_signals
from benchmark_recognition_open_set import temperature

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / 'model/runs/recognition'
OUTPUT = RUNS / 'unseen_id_audit_20261027'
BASE = RUNS / 'open_set_features_20261026'


def load(directory, name):
    with np.load(directory / f'{name}.npz') as handle:
        return {key: handle[key].copy() for key in handle.files}


def unknown_id_split(class_ids):
    counts = Counter(map(int, class_ids))
    ids = sorted(counts, key=lambda key: (-counts[key],
        hashlib.sha256(str(key).encode()).hexdigest()))
    groups = [[], []]
    total = [0, 0]
    for class_id in ids:
        side = 0 if total[0] <= total[1] else 1
        groups[side].append(class_id)
        total[side] += counts[class_id]
    return np.isin(class_ids, groups[0]), groups, total


def subset(data, mask):
    return {key: value[mask] for key, value in data.items()}


def score_verifier(name, feature_dir, known_cal_mask, device):
    known, unknown = load(feature_dir, 'validation-known'), load(feature_dir, 'validation-unknown')
    path = RUNS / name / 'best.pt'
    checkpoint = torch.load(path, map_location='cpu', weights_only=False)
    model = verifier.Verifier(checkpoint['config'].get('feature_dim',
        known['features'].shape[1])).to(device)
    model.load_state_dict(checkpoint['model']); model.eval()
    temp = temperature(known['logits'][known_cal_mask], known['class_ids'][known_cal_mask])
    return known, unknown, verifier.predict(model, known, device, temp), \
        verifier.predict(model, unknown, device, temp), str(path.relative_to(ROOT))


def score_unknown_head(known_cal_mask, device):
    known, unknown = load(BASE, 'validation-known'), load(BASE, 'validation-unknown')
    path = RUNS / 'unknown_head_20261027/best.pt'
    checkpoint = torch.load(path, map_location='cpu', weights_only=False)
    model = UnknownHead(known['features'].shape[1]).to(device)
    model.load_state_dict(checkpoint['model']); model.eval()
    temp = temperature(known['logits'][known_cal_mask], known['class_ids'][known_cal_mask])
    return known, unknown, unknown_signals(model, known, device, temp), \
        unknown_signals(model, unknown, device, temp), str(path.relative_to(ROOT))


def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    original_known = load(BASE, 'validation-known')
    original_unknown = load(BASE, 'validation-unknown')
    km = verifier.grouped_mask('validation', 'known', 0)
    um, id_groups, counts = unknown_id_split(original_unknown['class_ids'])
    if len(km) != len(original_known['class_ids']) or \
            len(um) != len(original_unknown['class_ids']) or \
            set(id_groups[0]) & set(id_groups[1]):
        raise ValueError('Split mismatch')
    candidates = {
        'original_verifier': lambda: score_verifier('class_conditioned_verifier_20261027',
            BASE, km, device),
        'color_verifier': lambda: score_verifier('class_conditioned_verifier_color_20261027',
            RUNS / 'pim_color_features_20261027', km, device),
        'unknown_head': lambda: score_unknown_head(km, device),
        'oe_verifier': lambda: score_verifier('class_conditioned_verifier_pim_oe_20261027',
            RUNS / 'pim_oe_features_20261027', km, device),
        'multilayer_verifier': lambda: score_verifier('class_conditioned_verifier_multilayer_20261027',
            RUNS / 'pim_multilayer_features_20261027', km, device),
        'dinov2_verifier': lambda: score_verifier('class_conditioned_verifier_dinov2_20261027',
            RUNS / 'pim_dinov2_features_20261027', km, device),
        'spatial_verifier': lambda: score_verifier('class_conditioned_verifier_spatial_20261027',
            RUNS / 'pim_spatial_features_20261027', km, device),
    }
    records = {}
    for name, scorer in candidates.items():
        known, unknown, ks, us, checkpoint = scorer()
        if not np.array_equal(known['class_ids'], original_known['class_ids']) or \
                not np.array_equal(unknown['class_ids'], original_unknown['class_ids']) or \
                not np.array_equal(known['image_ids'], original_known['image_ids']) or \
                not np.array_equal(unknown['image_ids'], original_unknown['image_ids']):
            raise ValueError(f'Feature row identity changed: {name}')
        ck, cu = subset(known, km), subset(unknown, um)
        rk, ru = subset(known, ~km), subset(unknown, ~um)
        verifier.CALIBRATION_KNOWN = ck
        threshold = verifier.select_threshold((ks[0][km], ks[1][km]),
            (us[0][um], us[1][um]))
        calibration = verifier.summarize(ck, cu, (ks[0][km], ks[1][km]),
            (us[0][um], us[1][um]), threshold)
        remainder = verifier.summarize(rk, ru, (ks[0][~km], ks[1][~km]),
            (us[0][~um], us[1][~um]), threshold)
        records[name] = {'checkpoint': checkpoint, 'threshold': threshold,
            'calibration': calibration, 'unseen_id_remainder': remainder}
        print(name, 'cal', round(calibration['known_correct_accept_rate'], 4),
            calibration['unknown_false_accept_count'], 'unseen',
            round(remainder['known_correct_accept_rate'], 4),
            remainder['unknown_false_accept_count'], flush=True)
    selected = max(records, key=lambda name: (records[name]['calibration']
        ['known_correct_accept_rate'], -records[name]['calibration']['known_wrong_accept_rate'],
        -records[name]['calibration']['unknown_false_accept_rate']))
    report = {'split': {'unknown_calibration_ids': sorted(id_groups[0]),
        'unknown_evaluation_ids': sorted(id_groups[1]),
        'unknown_calibration_count': counts[0], 'unknown_evaluation_count': counts[1],
        'known_rule': 'SHA-256 group_id parity 0 calibration, 1 evaluation'},
        'candidates': records, 'selected_on_calibration': selected,
        'test_used': False, 'previously_inspected_validation': True}
    OUTPUT.mkdir(exist_ok=True, parents=True)
    (OUTPUT / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('selected on calibration:', selected, flush=True)


if __name__ == '__main__':
    main()
