"""Benchmark ArcFace and SupCon heads over frozen FGVC-PIM ROI features.

All fitting and threshold selection use train/validation only. Test is loaded only
after the winning method and operating point have been written to disk.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from train_recognition_pim import ROOT, CLASSES

BASE = ROOT / 'model/runs/recognition/open_set_features_20261026'
OUT = ROOT / 'model/runs/recognition/open_set_benchmark_20261026'
IDS = np.array(CLASSES)


def load(split, kind):
    with np.load(BASE / f'{split}-{kind}.npz') as data:
        return {name: data[name].copy() for name in data.files}


def normalized_features(data):
    return F.normalize(torch.as_tensor(data['features'], dtype=torch.float32), dim=1)


class Projection(torch.nn.Module):
    def __init__(self, dimensions):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(dimensions, 256),
            torch.nn.ReLU(), torch.nn.Linear(256, 128))

    def forward(self, x):
        return F.normalize(self.net(x), dim=1)


def fit(method, x, labels, device, epochs, seed):
    torch.manual_seed(seed)
    projector = Projection(x.shape[1]).to(device)
    head = torch.nn.Parameter(torch.randn(7, 128, device=device)) if method == 'arcface' else None
    params = list(projector.parameters()) + ([head] if head is not None else [])
    optimizer = torch.optim.AdamW(params, lr=.001, weight_decay=.0001)
    data_hash = hashlib.sha256(x.numpy().tobytes() + np.asarray(labels).tobytes()).hexdigest()
    resume_path = OUT / f'{method}-last.pt'
    start = 0
    if resume_path.exists():
        saved = torch.load(resume_path, map_location=device, weights_only=False)
        if (saved['method'] != method or saved['epochs'] != epochs or
                saved['seed'] != seed or saved['n_train'] != len(x) or
                saved.get('data_hash', data_hash) != data_hash):
            raise ValueError(f'resume configuration mismatch: {resume_path}')
        projector.load_state_dict(saved['projection'])
        if head is not None:
            head.data.copy_(saved['head'])
        optimizer.load_state_dict(saved['optimizer'])
        torch.set_rng_state(saved['rng_cpu'].cpu())
        if device.type == 'cuda':
            torch.cuda.set_rng_state_all([state.cpu() for state in saved['rng_cuda']])
        start = saved['epoch'] + 1
        print(f'Resuming {method} epoch {start + 1}/{epochs}', flush=True)
    xx = x.to(device)
    yy = torch.as_tensor([CLASSES.index(int(v)) for v in labels], device=device)
    per_class = [torch.where(yy == k)[0] for k in range(7)]
    for epoch in range(start, epochs):
        projector.train()
        losses = []
        steps = math.ceil(len(x) / 112)
        for _ in range(steps):
            idx = torch.cat([pool[torch.randint(len(pool), (16,), device=device)]
                             for pool in per_class])
            idx = idx[torch.randperm(len(idx), device=device)]
            z = projector(xx[idx])
            y = yy[idx]
            if method == 'arcface':
                cosine = F.linear(z, F.normalize(head, dim=1)).clamp(-1 + 1e-6, 1 - 1e-6)
                target = cosine.gather(1, y[:, None])
                margin_cos = target * math.cos(.3) - torch.sqrt(1 - target.square()) * math.sin(.3)
                logits = cosine.scatter(1, y[:, None], margin_cos) * 30
                loss = F.cross_entropy(logits, y)
            else:
                similarities = z @ z.T / .1
                eye = torch.eye(len(idx), device=device, dtype=torch.bool)
                positive = (y[:, None] == y[None, :]) & ~eye
                similarities = similarities.masked_fill(eye, -1e9)
                log_prob = similarities - torch.logsumexp(similarities, dim=1, keepdim=True)
                loss = -(log_prob * positive).sum(1).div(positive.sum(1)).mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
        print(f'{method} epoch {epoch + 1}/{epochs} loss={np.mean(losses):.4f}', flush=True)
        state = {'method': method, 'epochs': epochs, 'seed': seed, 'n_train': len(x),
                 'data_hash': data_hash,
                 'epoch': epoch, 'projection': projector.state_dict(),
                 'head': head.detach() if head is not None else None,
                 'optimizer': optimizer.state_dict(), 'rng_cpu': torch.get_rng_state(),
                 'rng_cuda': torch.cuda.get_rng_state_all() if device.type == 'cuda' else []}
        temporary = resume_path.with_suffix('.tmp')
        torch.save(state, temporary)
        os.replace(temporary, resume_path)
    projector.eval()
    return projector


def embed(model, data, device):
    with torch.inference_mode():
        x = normalized_features(data)
        return torch.cat([model(batch.to(device)).cpu() for batch in x.split(1024)]).numpy()


def temperature(logits, labels):
    y = torch.as_tensor([CLASSES.index(int(v)) for v in labels])
    x = torch.as_tensor(logits, dtype=torch.float32)
    log_t = torch.nn.Parameter(torch.zeros(()))
    optimizer = torch.optim.LBFGS([log_t], lr=.1, max_iter=100)

    def closure():
        optimizer.zero_grad()
        loss = F.cross_entropy(x / log_t.exp(), y)
        loss.backward()
        return loss

    optimizer.step(closure)
    return float(log_t.exp().detach().clamp(.05, 100))


def signals(data, embedding, prototypes, temp):
    logits = torch.as_tensor(data['logits'], dtype=torch.float32)
    probs = F.softmax(logits / temp, dim=1).numpy()
    predicted = probs.argmax(1)
    sim = embedding @ prototypes.T
    return probs[np.arange(len(probs)), predicted], sim[np.arange(len(sim)), predicted], predicted


def choose_threshold(known, unknown, target_far=.01):
    kp, ks, ki = known
    up, us, _ = unknown
    truth = np.array([CLASSES.index(int(v)) for v in validation_known['class_ids']])
    best = None
    for p in np.unique(np.quantile(np.r_[kp, up], np.linspace(0, 1, 101))):
        for s in np.unique(np.quantile(np.r_[ks, us], np.linspace(0, 1, 101))):
            unknown_far = np.mean((up >= p) & (us >= s))
            if unknown_far > target_far:
                continue
            correct_accept = np.mean((kp >= p) & (ks >= s) & (ki == truth))
            wrong_accept = np.mean((kp >= p) & (ks >= s) & (ki != truth))
            key = (correct_accept, -wrong_accept, -unknown_far)
            if best is None or key > best[0]:
                best = (key, float(p), float(s), float(unknown_far), float(wrong_accept))
    if best is None:
        raise RuntimeError('No threshold meets validation unknown FAR target')
    return {'probability_min': best[1], 'cosine_min': best[2],
            'known_correct_accept_rate': best[0][0],
            'known_wrong_accept_rate': best[4], 'unknown_false_accept_rate': best[3]}


def metrics(known, unknown, truth, threshold):
    kp, ks, ki = known
    up, us, _ = unknown
    p, s = threshold['probability_min'], threshold['cosine_min']
    ka = (kp >= p) & (ks >= s)
    ua = (up >= p) & (us >= s)
    score = np.r_[kp * (ks + 1) / 2, up * (us + 1) / 2]
    labels = np.r_[np.zeros(len(kp)), np.ones(len(up))]
    order = np.argsort(-(-score), kind='stable')
    sorted_labels = labels[order]
    positives = sorted_labels.sum()
    precision = np.cumsum(sorted_labels) / np.arange(1, len(labels) + 1)
    ap = float((precision * sorted_labels).sum() / positives)
    # Mann-Whitney AUROC with average ranks for score ties.
    unknown_score = -score
    sorted_score = np.argsort(unknown_score, kind='stable')
    ranks = np.empty(len(labels), dtype=float)
    position = 0
    while position < len(labels):
        end = position + 1
        while end < len(labels) and unknown_score[sorted_score[end]] == unknown_score[sorted_score[position]]:
            end += 1
        ranks[sorted_score[position:end]] = (position + end + 1) / 2
        position = end
    auc = float((ranks[labels == 1].sum() - positives * (positives + 1) / 2) /
                (positives * (len(labels) - positives)))
    return {'known_correct_accept_rate': float(np.mean(ka & (ki == truth))),
            'known_wrong_accept_rate': float(np.mean(ka & (ki != truth))),
            'unknown_false_accept_rate': float(np.mean(ua)),
            'unknown_recall': float(np.mean(~ua)),
            'unknown_auroc': auc,
            'unknown_aupr': ap}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=25)
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
    args = parser.parse_args()
    device = torch.device('cuda' if args.device == 'auto' and torch.cuda.is_available() else
                          'cpu' if args.device == 'auto' else args.device)
    global validation_known
    train = load('train', 'known')
    validation_known = load('validation', 'known')
    validation_unknown = load('validation', 'unknown')
    x = normalized_features(train)
    temp = temperature(validation_known['logits'], validation_known['class_ids'])
    OUT.mkdir(parents=True, exist_ok=True)
    candidates = {}
    for method in ('arcface', 'supcon'):
        model = fit(method, x, train['class_ids'], device, args.epochs, 20261026)
        train_embed = embed(model, train, device)
        prototypes = np.stack([train_embed[train['class_ids'] == cid].mean(0) for cid in CLASSES])
        prototypes /= np.linalg.norm(prototypes, axis=1, keepdims=True)
        kv = signals(validation_known, embed(model, validation_known, device), prototypes, temp)
        uv = signals(validation_unknown, embed(model, validation_unknown, device), prototypes, temp)
        threshold = choose_threshold(kv, uv)
        truth = np.array([CLASSES.index(int(v)) for v in validation_known['class_ids']])
        result = metrics(kv, uv, truth, threshold)
        torch.save({'projection': model.cpu().state_dict(), 'prototypes': prototypes,
                    'method': method, 'epochs': args.epochs, 'seed': 20261026}, OUT / f'{method}.pt')
        candidates[method] = {'threshold': threshold, 'validation': result}
        print(method, json.dumps(candidates[method]), flush=True)
    winner = max(candidates, key=lambda m: (candidates[m]['validation']['known_correct_accept_rate'],
        -candidates[m]['validation']['known_wrong_accept_rate']))
    selected = {'winner': winner, 'temperature': temp, 'target_validation_unknown_far': .01,
                'candidate_results': candidates, 'feature_policy': 'frozen PIM projection heads'}
    (OUT / 'selection-validation.json').write_text(json.dumps(selected, indent=2) + '\n')
    # The held-out test split is first read after the method and thresholds are fixed.
    checkpoint = torch.load(OUT / f'{winner}.pt', map_location='cpu', weights_only=False)
    model = Projection(x.shape[1]).to(device)
    model.load_state_dict(checkpoint['projection'])
    model.eval()
    prototypes = checkpoint['prototypes']
    test_known = load('test', 'known')
    test_unknown = load('test', 'unknown')
    kt = signals(test_known, embed(model, test_known, device), prototypes, temp)
    ut = signals(test_unknown, embed(model, test_unknown, device), prototypes, temp)
    truth = np.array([CLASSES.index(int(v)) for v in test_known['class_ids']])
    result = {'selected_method': winner, 'threshold': candidates[winner]['threshold'],
              'test': metrics(kt, ut, truth, candidates[winner]['threshold']),
              'sample_counts': {'known': len(test_known['class_ids']),
                                'unknown': len(test_unknown['class_ids'])}}
    (OUT / 'test-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print('TEST', json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
