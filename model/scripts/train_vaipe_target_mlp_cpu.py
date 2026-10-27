"""Research-only nonlinear target verifier on class-disjoint VAIPE identities."""
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from scipy.special import softmax

import train_recognition_verifier as base
from benchmark_recognition_open_set import CLASSES, temperature
from evaluate_recognition_unseen_ids import load, subset, unknown_id_split
from evaluate_vaipe_target_gate_cpu import choose_target_threshold

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ROOT / 'model/runs/recognition/open_set_features_20261026'
OUT = ROOT / 'model/runs/recognition/vaipe_target_mlp_cpu_20261027'


def unit(x):
    x = x.astype(np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(min=1e-9)


def main():
    torch.set_num_threads(4)
    torch.manual_seed(20261027)
    np.random.seed(20261027)
    kt, ut, kv, uv = (load(FEATURES, name) for name in
        ('train-known', 'train-unknown', 'validation-known', 'validation-unknown'))
    uv = subset(uv, uv['class_ids'] != 107)
    validation_unknown_ids = set(map(int, uv['class_ids']))
    negative_ids = sorted(set(map(int, ut['class_ids'])) - validation_unknown_ids - {107})
    ut = subset(ut, np.isin(ut['class_ids'], negative_ids))
    assert set(map(int, ut['class_ids'])).isdisjoint(validation_unknown_ids)
    x = torch.from_numpy(unit(np.concatenate([kt['features'], ut['features']])))
    ids = np.concatenate([kt['class_ids'], ut['class_ids']])
    y = torch.from_numpy(np.stack([(ids == c).astype(np.float32) for c in CLASSES], axis=1))
    weights = []
    for c in CLASSES:
        pos = ids == c
        w = np.where(pos, .5 / pos.sum(), .5 / (~pos).sum()) * len(ids)
        weights.append(w.astype(np.float32))
    w = torch.from_numpy(np.stack(weights, axis=1))
    model = torch.nn.Sequential(torch.nn.Linear(x.shape[1], 128), torch.nn.ReLU(),
        torch.nn.Linear(128, len(CLASSES)))
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.01)
    for epoch in range(40):
        model.train()
        order = torch.randperm(len(x))
        for indices in order.split(512):
            logits = model(x[indices])
            loss = (F.binary_cross_entropy_with_logits(logits, y[indices], reduction='none')
                * w[indices]).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        if (epoch + 1) % 10 == 0:
            print('epoch', epoch + 1, 'loss', float(loss.detach()), flush=True)
    model.eval()
    km = base.grouped_mask('validation', 'known', 0)
    um, id_groups, counts = unknown_id_split(uv['class_ids'])
    assert len(km) == len(kv['class_ids']) and len(um) == len(uv['class_ids'])
    temp = temperature(kv['logits'][km], kv['class_ids'][km])

    def scores(data):
        z = torch.from_numpy(unit(data['features']))
        with torch.inference_mode():
            verify = torch.cat([model(batch).sigmoid() for batch in z.split(1024)]).numpy()
        classifier = softmax(data['logits'].astype(np.float64) / temp, axis=1)
        return classifier * verify, classifier.argmax(1)

    ks, kp = scores(kv)
    us, up = scores(uv)
    truth = np.array([CLASSES.index(int(v)) for v in kv['class_ids']])
    result = {}
    for i, c in enumerate(CLASSES):
        t = choose_target_threshold(ks[km, i], kp[km], truth[km],
            us[um, i], up[um], i, 0)
        def part(kmask, umask):
            positive = truth[kmask] == i
            accepted = (kp[kmask] == i) & (ks[kmask, i] >= t)
            false_unknown = (up[umask] == i) & (us[umask, i] >= t)
            return {'correct_accepted': int((positive & accepted).sum()),
                'known_target_count': int(positive.sum()),
                'other_known_accepted': int((~positive & accepted).sum()),
                'unknown_accepted': int(false_unknown.sum()),
                'unknown_count': int(umask.sum())}
        result[str(c)] = {'threshold': float(t), 'calibration': part(km, um),
            'unseen_ids': part(~km, ~um)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'validation-results.json').write_text(json.dumps({
        'method': 'target MLP 256-128-7 on frozen PIM embeddings',
        'train_known_count': len(kt['class_ids']), 'train_negative_count': len(ut['class_ids']),
        'negative_train_ids': negative_ids, 'unknown_calibration_ids': id_groups[0],
        'unknown_evaluation_ids': id_groups[1], 'unknown_counts': counts,
        'epochs': 40, 'seed': 20261027, 'temperature': float(temp),
        'per_target': result, 'device': 'cpu', 'test_used': False,
        'validation_previously_inspected': True}, indent=2) + '\n')
    torch.save({'model': model.state_dict(), 'classes': CLASSES,
        'architecture': 'Linear(256,128)-ReLU-Linear(128,7)'}, OUT / 'model.pt')
    for c in CLASSES:
        print(c, result[str(c)]['unseen_ids'], flush=True)


if __name__ == '__main__':
    main()
