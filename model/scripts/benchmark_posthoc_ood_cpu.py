"""Training-free post-hoc OOD scores on frozen PIM features, CPU only.

Same protocol as evaluate_vaipe_target_gate_cpu.py: 107 excluded, known
validation split by group hash, unknown validation split by disjoint IDs.
Threshold chosen on calibration (unknown FAR <= 1%), reported on unseen IDs.
Statistics are fit on train only; no test access.
"""
import json
from pathlib import Path

import numpy as np
import torch

import train_recognition_verifier as gate
from benchmark_recognition_open_set import CLASSES
from evaluate_recognition_unseen_ids import load, subset, unknown_id_split

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / 'model/runs/recognition'
OUT = RUNS / 'posthoc_ood_cpu_20261027'
CLASS_CONTEXT_ONLY = 107


def l2(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(1e-12)


def class_index(ids):
    return np.array([CLASSES.index(int(v)) for v in ids])


def gaussian(train_x, train_y, n_class):
    means = np.stack([train_x[train_y == c].mean(0) for c in range(n_class)])
    centered = train_x - means[train_y]
    cov = centered.T @ centered / len(train_x)
    precision = np.linalg.pinv(cov + 1e-6 * np.eye(cov.shape[0]))
    return means, precision


def maha(x, means, precision):
    diff = x[:, None, :] - means[None]
    return np.einsum('ncd,de,nce->nc', diff, precision, diff)


def scores(train_known, train_unknown, data, held_out_ids=()):
    """Return {name: (score, prediction)}; higher score means more likely known."""
    tx, ty = l2(train_known['features']), class_index(train_known['class_ids'])
    x, logits = l2(data['features']), data['logits']
    pred = logits.argmax(1)
    out = {}
    out['msp'] = torch.softmax(torch.as_tensor(logits), 1).numpy().max(1)
    out['energy'] = torch.logsumexp(torch.as_tensor(logits), 1).numpy()
    means, precision = gaussian(tx, ty, len(CLASSES))
    d = maha(x, means, precision)
    out['mahalanobis'] = -d.min(1)
    out['mahalanobis_pred'] = -d[np.arange(len(x)), pred]
    # Relative Mahalanobis (Ren et al. 2021): subtract a class-agnostic background.
    bg_mean = tx.mean(0, keepdims=True)
    bg_prec = np.linalg.pinv(np.cov(tx, rowvar=False) + 1e-6 * np.eye(tx.shape[1]))
    bg = maha(x, bg_mean, bg_prec)[:, 0]
    out['rel_mahalanobis'] = -(d[np.arange(len(x)), pred] - bg)
    # Negative-aware: known-class distance vs. nearest train-unknown ID gaussian.
    ux = l2(train_unknown['features'])
    uid = train_unknown['class_ids']
    keep_ids = [i for i in np.unique(uid) if i != CLASS_CONTEXT_ONLY and i not in held_out_ids and (uid == i).sum() >= 5]
    umeans = np.stack([ux[uid == i].mean(0) for i in keep_ids])
    du = maha(x, umeans, precision).min(1)
    out['maha_vs_negatives'] = du - d[np.arange(len(x)), pred]
    # kNN cosine to train-known of predicted class (Sun et al. 2022 uses all train).
    sims = x @ tx.T
    for k in (1, 10):
        out[f'knn{k}'] = -(1 - np.sort(sims, 1)[:, -k])
    # ViM (Wang et al. 2022) on PIM features.
    centered = tx - tx.mean(0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    ns = vt[12:].T
    resid = lambda z: np.linalg.norm((z - tx.mean(0)) @ ns, axis=1)
    alpha = train_known['logits'].max(1).mean() / resid(tx).mean()
    vlogit = alpha * resid(x)
    out['vim'] = -(-torch.logsumexp(torch.as_tensor(logits), 1).numpy() + vlogit)
    return {k: (v, pred) for k, v in out.items()}


def main():
    torch.set_num_threads(4)
    feature_dir = RUNS / 'open_set_features_20261026'
    train_known = load(feature_dir, 'train-known')
    train_unknown = load(feature_dir, 'train-unknown')
    known = load(feature_dir, 'validation-known')
    unknown_all = load(feature_dir, 'validation-unknown')
    unknown = subset(unknown_all, unknown_all['class_ids'] != CLASS_CONTEXT_ONLY)
    km = gate.grouped_mask('validation', 'known', 0)
    um, ids, _ = unknown_id_split(unknown['class_ids'])
    if set(ids[0]) & set(ids[1]) or set(np.unique(train_unknown['class_ids'])) & \
            set(map(int, unknown['class_ids'][~um])):
        print('note: some unseen-side unknown IDs also appear in train-unknown negatives')
    held = set(map(int, unknown['class_ids']))  # never use any validation-unknown ID as negative
    print('negative IDs kept:', len(set(map(int, train_unknown['class_ids'])) - held - {CLASS_CONTEXT_ONLY}))
    ks = scores(train_known, train_unknown, known, held)
    us = scores(train_known, train_unknown, unknown, held)
    results = {}
    for name in ks:
        k, u = ks[name], us[name]
        gate.CALIBRATION_KNOWN = subset(known, km)
        try:
            t = gate.select_threshold((k[0][km], k[1][km]), (u[0][um], u[1][um]))
        except RuntimeError:
            results[name] = 'no threshold'; continue
        r = gate.summarize(subset(known, ~km), subset(unknown, ~um),
                           (k[0][~km], k[1][~km]), (u[0][~um], u[1][~um]), t)
        results[name] = r
        pc = ' '.join(f"{c}:{v['correct_accepted']}/{v['total']}" for c, v in r['per_class'].items())
        print(f"{name:20s} known {r['known_correct_accept_rate']:.2%}  "
              f"unknown {r['unknown_false_accept_count']}/{r['unknown_count']}  {pc}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'results.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
