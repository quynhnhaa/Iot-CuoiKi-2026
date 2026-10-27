"""Train an embedding-based known/unknown rejector, evaluate on group-held validation.

The existing test split is intentionally never loaded in this experiment.
"""
import argparse
import csv
import hashlib
import json
import os

import numpy as np
import torch
import torch.nn.functional as F

from benchmark_recognition_open_set import (CLASSES, OUT as PREVIOUS, Projection,
    embed, load, normalized_features, signals, temperature)
from train_recognition_pim import ROOT, ROI
from extract_recognition_features import UNKNOWN

OUT = ROOT / 'model/runs/recognition/negative_rejector_20261026'


class Rejector(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(256, 128), torch.nn.ReLU(),
            torch.nn.Dropout(.15), torch.nn.Linear(128, 1))

    def forward(self, x):
        return self.net(x).flatten()


def groups(split, kind):
    path = (ROI if kind == 'known' else UNKNOWN) / f'{split}.csv'
    with path.open(newline='') as f:
        return np.array([row['group_id'] for row in csv.DictReader(f)])


def subset(data, mask):
    return {k: v[mask] for k, v in data.items()}


def part_mask(values, part):
    return np.array([int(hashlib.sha256(value.encode()).hexdigest(), 16) % 2 == part for value in values])


def auroc(known_score, unknown_score):
    score = np.r_[known_score, unknown_score]
    y = np.r_[np.ones(len(known_score)), np.zeros(len(unknown_score))]
    order = np.argsort(score, kind='stable')
    ranks = np.empty(len(score), dtype=float)
    pos = 0
    while pos < len(score):
        end = pos + 1
        while end < len(score) and score[order[end]] == score[order[pos]]:
            end += 1
        ranks[order[pos:end]] = (pos + end + 1) / 2
        pos = end
    n = len(known_score); m = len(unknown_score)
    return float((ranks[y == 1].sum() - n * (n + 1) / 2) / (n * m))


def predict(model, data, device):
    x = normalized_features(data)
    with torch.inference_mode():
        return torch.cat([model(batch.to(device)).sigmoid().cpu() for batch in x.split(1024)]).numpy()


def classifier(data, temp):
    probs = F.softmax(torch.as_tensor(data['logits'], dtype=torch.float32) / temp, dim=1).numpy()
    return probs.max(1), probs.argmax(1)


def threshold_for(known, unknown, target=.01):
    candidates = np.unique(np.r_[known, unknown])
    best = None
    for value in candidates:
        far = np.mean(unknown >= value)
        if far > target:
            continue
        recall = np.mean(known >= value)
        key = (recall, -far)
        if best is None or key > best[0]:
            best = (key, value)
    return float(best[1])


def evaluate(known, unknown, known_score, unknown_score, threshold):
    k_p, k_idx = classifier(known, TEMPERATURE)
    u_p, _ = classifier(unknown, TEMPERATURE)
    known_accept = k_p * known_score >= threshold
    unknown_accept = u_p * unknown_score >= threshold
    truth = np.array([CLASSES.index(int(v)) for v in known['class_ids']])
    return {'known_correct_accept_rate': float(np.mean(known_accept & (k_idx == truth))),
            'known_wrong_accept_rate': float(np.mean(known_accept & (k_idx != truth))),
            'unknown_false_accept_rate': float(np.mean(unknown_accept)),
            'knownness_auroc': auroc(known_score, unknown_score),
            'known_count': len(known_score), 'unknown_count': len(unknown_score)}


def baseline_pair(cal_k, cal_u, hold_k, hold_u, device):
    previous = json.loads((PREVIOUS / 'selection-validation.json').read_text())
    saved = torch.load(PREVIOUS / f"{previous['winner']}.pt", map_location='cpu', weights_only=False)
    model = Projection(256).to(device)
    model.load_state_dict(saved['projection']); model.eval()
    prototypes = saved['prototypes']
    ck = signals(cal_k, embed(model, cal_k, device), prototypes, TEMPERATURE)
    cu = signals(cal_u, embed(model, cal_u, device), prototypes, TEMPERATURE)
    truth = np.array([CLASSES.index(int(v)) for v in cal_k['class_ids']])
    best = None
    for p in np.unique(np.quantile(np.r_[ck[0], cu[0]], np.linspace(0, 1, 101))):
        for s in np.unique(np.quantile(np.r_[ck[1], cu[1]], np.linspace(0, 1, 101))):
            far = np.mean((cu[0] >= p) & (cu[1] >= s))
            if far > .01:
                continue
            right = np.mean((ck[0] >= p) & (ck[1] >= s) & (ck[2] == truth))
            key = (right, -far)
            if best is None or key > best[0]:
                best = (key, float(p), float(s))
    p, s = best[1:]
    hk = signals(hold_k, embed(model, hold_k, device), prototypes, TEMPERATURE)
    hu = signals(hold_u, embed(model, hold_u, device), prototypes, TEMPERATURE)
    htruth = np.array([CLASSES.index(int(v)) for v in hold_k['class_ids']])
    accept_k = (hk[0] >= p) & (hk[1] >= s)
    accept_u = (hu[0] >= p) & (hu[1] >= s)
    return {'method': previous['winner'], 'probability_min': p, 'cosine_min': s,
        'calibration_unknown_false_accept_rate': float(np.mean((cu[0] >= p) & (cu[1] >= s))),
        'heldout_validation': {
            'known_correct_accept_rate': float(np.mean(accept_k & (hk[2] == htruth))),
            'known_wrong_accept_rate': float(np.mean(accept_k & (hk[2] != htruth))),
            'unknown_false_accept_rate': float(np.mean(accept_u)),
            'known_count': len(hk[0]), 'unknown_count': len(hu[0])}}


def per_class_policy(cal_k, cal_u, hold_k, hold_u, ck, cu, hk, hu):
    cp, ci = classifier(cal_k, TEMPERATURE)
    up, ui = classifier(cal_u, TEMPERATURE)
    hp, hi = classifier(hold_k, TEMPERATURE)
    vp, vi = classifier(hold_u, TEMPERATURE)
    cy = np.array([CLASSES.index(int(v)) for v in cal_k['class_ids']])
    hy = np.array([CLASSES.index(int(v)) for v in hold_k['class_ids']])
    cutoffs = []
    negative_counts = []
    for index in range(len(CLASSES)):
        positives = (ci == index) & (cy == index)
        negatives = ui == index
        negative_counts.append(int(negatives.sum()))
        if not positives.any() or negatives.sum() < 20:
            cutoffs.append(float('inf'))
        else:
            cutoffs.append(threshold_for(cp[positives] * ck[positives],
                                         up[negatives] * cu[negatives]))
    chosen = np.array(cutoffs)
    accepted_k = hp * hk >= chosen[hi]
    accepted_u = vp * hu >= chosen[vi]
    return {'thresholds_by_class_id': {str(cid): value for cid, value in zip(CLASSES, cutoffs)},
        'calibration_unknown_predicted_counts_by_class_id': {
            str(cid): count for cid, count in zip(CLASSES, negative_counts)},
        'heldout_validation': {
            'known_correct_accept_rate': float(np.mean(accepted_k & (hi == hy))),
            'known_wrong_accept_rate': float(np.mean(accepted_k & (hi != hy))),
            'unknown_false_accept_rate': float(np.mean(accepted_u)),
            'correct_accept_by_class_id': {str(cid): {
                'count': int(((hy == index) & (hi == index) & accepted_k).sum()),
                'total': int((hy == index).sum())}
                for index, cid in enumerate(CLASSES)},
            'unknown_accepted_count': int(accepted_u.sum()),
            'known_count': len(hk), 'unknown_count': len(hu)}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
    parser.add_argument('--unknown-policy', choices=['class-disjoint', 'all-train'],
                        default='class-disjoint')
    args = parser.parse_args()
    device = torch.device('cuda' if args.device == 'auto' and torch.cuda.is_available() else
                          'cpu' if args.device == 'auto' else args.device)
    global TEMPERATURE, OUT
    OUT = ROOT / ('model/runs/recognition/negative_rejector_class_disjoint_20261026'
                  if args.unknown_policy == 'class-disjoint' else
                  'model/runs/recognition/negative_rejector_20261026')
    train_known = load('train', 'known'); train_unknown = load('train', 'unknown')
    val_known = load('validation', 'known'); val_unknown = load('validation', 'unknown')
    negative_ids = sorted(set(int(x) for x in train_unknown['class_ids']))
    if args.unknown_policy == 'class-disjoint':
        validation_ids = set(int(x) for x in val_unknown['class_ids'])
        negative_ids = [value for value in negative_ids if value not in validation_ids]
        train_unknown = subset(train_unknown, np.isin(train_unknown['class_ids'], negative_ids))
        if len(negative_ids) < 2 or len(train_unknown['class_ids']) < 100:
            raise ValueError('too few class-disjoint negative training examples')
    gk = groups('validation', 'known'); gu = groups('validation', 'unknown')
    if len(gk) != len(val_known['class_ids']) or len(gu) != len(val_unknown['class_ids']):
        raise ValueError('manifest and feature row counts differ')
    calibration_known = subset(val_known, part_mask(gk, 0))
    calibration_unknown = subset(val_unknown, part_mask(gu, 0))
    holdout_known = subset(val_known, part_mask(gk, 1))
    holdout_unknown = subset(val_unknown, part_mask(gu, 1))
    TEMPERATURE = temperature(calibration_known['logits'], calibration_known['class_ids'])
    xk = normalized_features(train_known).to(device)
    xu = normalized_features(train_unknown).to(device)
    source_hash = hashlib.sha256(xk.cpu().numpy().tobytes() + xu.cpu().numpy().tobytes()).hexdigest()
    torch.manual_seed(20261026)
    model = Rejector().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0003, weight_decay=.001)
    OUT.mkdir(parents=True, exist_ok=True)
    last = OUT / 'last.pt'; best_path = OUT / 'best.pt'
    start = 0; best_auc = -1
    if last.exists():
        ck = torch.load(last, map_location=device, weights_only=False)
        if ck['epochs'] != args.epochs or ck['source_hash'] != source_hash:
            raise ValueError('resume config/data mismatch')
        model.load_state_dict(ck['model']); optimizer.load_state_dict(ck['optimizer'])
        torch.set_rng_state(ck['rng_cpu'].cpu())
        if device.type == 'cuda':
            torch.cuda.set_rng_state_all([v.cpu() for v in ck['rng_cuda']])
        start = ck['epoch'] + 1; best_auc = ck['best_auc']
        print(f'Resuming epoch {start + 1}/{args.epochs}', flush=True)
    for epoch in range(start, args.epochs):
        model.train(); losses = []
        for _ in range(80):
            a = xk[torch.randint(len(xk), (128,), device=device)]
            b = xu[torch.randint(len(xu), (128,), device=device)]
            batch = torch.cat([a, b]); target = torch.cat([
                torch.ones(len(a), device=device), torch.zeros(len(b), device=device)])
            loss = F.binary_cross_entropy_with_logits(model(batch), target)
            optimizer.zero_grad(); loss.backward(); optimizer.step(); losses.append(loss.item())
        model.eval()
        ks = predict(model, calibration_known, device)
        us = predict(model, calibration_unknown, device)
        auc = auroc(ks, us)
        if auc > best_auc:
            best_auc = auc
            temp = best_path.with_suffix('.tmp')
            torch.save({'model': model.state_dict(), 'epoch': epoch, 'calibration_auc': auc,
                        'source_hash': source_hash}, temp)
            os.replace(temp, best_path)
        ck = {'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
              'epoch': epoch, 'epochs': args.epochs, 'best_auc': best_auc,
              'source_hash': source_hash, 'rng_cpu': torch.get_rng_state(),
              'rng_cuda': torch.cuda.get_rng_state_all() if device.type == 'cuda' else []}
        temp = last.with_suffix('.tmp'); torch.save(ck, temp); os.replace(temp, last)
        print(f'epoch {epoch + 1}/{args.epochs} loss={np.mean(losses):.4f} calibration AUC={auc:.4f}', flush=True)
    best = torch.load(best_path, map_location=device, weights_only=False)
    model.load_state_dict(best['model']); model.eval()
    ck = predict(model, calibration_known, device)
    cu = predict(model, calibration_unknown, device)
    hk = predict(model, holdout_known, device)
    hu = predict(model, holdout_unknown, device)
    cp, _ = classifier(calibration_known, TEMPERATURE)
    up, _ = classifier(calibration_unknown, TEMPERATURE)
    threshold = threshold_for(cp * ck, up * cu)
    results = {'source_hash': source_hash, 'best_epoch': best['epoch'] + 1,
        'unknown_policy': args.unknown_policy, 'negative_train_ids': negative_ids,
        'negative_train_count': len(train_unknown['class_ids']),
        'validation_unknown_ids': len(set(int(x) for x in val_unknown['class_ids'])),
        'temperature_from_calibration_groups': TEMPERATURE, 'threshold': threshold,
        'calibration': evaluate(calibration_known, calibration_unknown, ck, cu, threshold),
        'heldout_validation': evaluate(holdout_known, holdout_unknown, hk, hu, threshold),
        'per_class_threshold_policy': per_class_policy(calibration_known, calibration_unknown,
            holdout_known, holdout_unknown, ck, cu, hk, hu),
        'frozen_supcon_baseline_same_groups': baseline_pair(calibration_known, calibration_unknown,
            holdout_known, holdout_unknown, device),
        'test_used': False, 'split_rule': 'sha256(group_id) parity; 0 calibration, 1 heldout'}
    (OUT / 'validation-results.json').write_text(json.dumps(results, indent=2) + '\n')
    with (OUT / 'heldout-validation-predictions.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['kind', 'image_id', 'annotation_index',
            'true_id', 'predicted_id', 'knownness', 'classifier_probability', 'score', 'accepted'])
        writer.writeheader()
        for kind, data, knownness in [('known', holdout_known, hk),
                                      ('unknown', holdout_unknown, hu)]:
            probability, index = classifier(data, TEMPERATURE)
            for i in range(len(knownness)):
                score = float(probability[i] * knownness[i])
                writer.writerow({'kind': kind, 'image_id': data['image_ids'][i],
                    'annotation_index': int(data['annotation_indices'][i]),
                    'true_id': int(data['class_ids'][i]),
                    'predicted_id': CLASSES[index[i]], 'knownness': float(knownness[i]),
                    'classifier_probability': float(probability[i]), 'score': score,
                    'accepted': score >= threshold})
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    main()
