"""Train class verifier with diverse negative IDs, hold out evaluation IDs entirely.

Calibration unknown IDs can occur in negative train, but validation images and
groups do not. Evaluation unknown IDs are absent from train and calibration.
This is exploratory validation only; no test is read.
"""
import hashlib
import json
import os
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

import train_recognition_verifier as base
from benchmark_recognition_open_set import CLASSES, normalized_features, temperature
from evaluate_recognition_unseen_ids import unknown_id_split

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ROOT / 'model/runs/recognition/open_set_features_20261026'
OUT = ROOT / 'model/runs/recognition/verifier_diverse_unknown_20261027'
EPOCHS = 30
SEED = 20261027


def save(payload, path):
    temp = path.with_suffix('.tmp')
    torch.save(payload, temp)
    os.replace(temp, path)


def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    base.FEATURE_DIR = FEATURES
    kt, ut, kv, uv = (base.load(split, kind) for split, kind in
        (('train', 'known'), ('train', 'unknown'),
         ('validation', 'known'), ('validation', 'unknown')))
    km = base.grouped_mask('validation', 'known', 0)
    um, id_groups, counts = unknown_id_split(uv['class_ids'])
    evaluation_ids = set(id_groups[1])
    train_mask = ~np.isin(ut['class_ids'], list(evaluation_ids))
    ut = base.subset(ut, train_mask)
    negative_ids = sorted(set(map(int, ut['class_ids'])))
    if set(negative_ids) & evaluation_ids:
        raise ValueError('Evaluation unknown IDs leaked into train')
    ck, cu = base.subset(kv, km), base.subset(uv, um)
    rk, ru = base.subset(kv, ~km), base.subset(uv, ~um)
    temp = temperature(ck['logits'], ck['class_ids'])
    xk, xu = normalized_features(kt).to(device), normalized_features(ut).to(device)
    yk = torch.tensor([CLASSES.index(int(value)) for value in kt['class_ids']],
                      device=device)
    known_pools = [torch.where(yk == index)[0] for index in range(len(CLASSES))]
    unknown_labels = torch.tensor(ut['class_ids'].astype(np.int64), device=device)
    unknown_pools = [torch.where(unknown_labels == class_id)[0] for class_id in negative_ids]
    config = {'epochs': EPOCHS, 'seed': SEED, 'negative_train_ids': negative_ids,
        'negative_train_count': len(xu), 'unknown_calibration_ids': sorted(id_groups[0]),
        'unknown_evaluation_ids': sorted(id_groups[1]), 'known_train_count': len(xk),
        'data_hash': hashlib.sha256(xk.cpu().numpy().tobytes() + xu.cpu().numpy().tobytes() +
            ut['class_ids'].tobytes()).hexdigest(), 'learning_rate': .0003,
        'steps_per_epoch': 80, 'known_per_class_per_step': 16,
        'negative_per_step': 112, 'positive_weight': 6.0,
        'negative_sampling': 'uniform class ID', 'device': str(device)}
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / 'run-manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != config:
        raise ValueError('Configuration or data changed')
    manifest_path.write_text(json.dumps(config, indent=2) + '\n')
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    if device.type == 'cuda':
        torch.cuda.manual_seed_all(SEED)
    model = base.Verifier(xk.shape[1]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config['learning_rate'],
                                   weight_decay=.001)
    last_path, best_path = OUT / 'last.pt', OUT / 'best.pt'
    start, best_metric = 0, -1.0
    if last_path.exists():
        saved = torch.load(last_path, map_location='cpu', weights_only=False)
        if saved['config'] != config:
            raise ValueError('Checkpoint mismatch')
        model.load_state_dict(saved['model']); optimizer.load_state_dict(saved['optimizer'])
        torch.set_rng_state(saved['rng_torch'])
        np.random.set_state(saved['rng_numpy']); random.setstate(saved['rng_python'])
        if device.type == 'cuda':
            torch.cuda.set_rng_state_all(saved['rng_cuda'])
        start, best_metric = saved['epoch']+1, saved['best_metric']
        print(f'Resuming epoch {start+1}/{EPOCHS}', flush=True)
    base.CALIBRATION_KNOWN = ck
    for epoch in range(start, EPOCHS):
        model.train(); losses = []
        for _ in range(config['steps_per_epoch']):
            known_indices = torch.cat([pool[torch.randint(len(pool), (16,), device=device)]
                for pool in known_pools])
            chosen_classes = torch.randint(len(unknown_pools), (112,), device=device)
            negative_indices = torch.stack([unknown_pools[int(cls)][torch.randint(
                len(unknown_pools[int(cls)]), (1,), device=device)][0]
                for cls in chosen_classes])
            batch = torch.cat([xk[known_indices], xu[negative_indices]])
            labels = torch.zeros((len(batch), len(CLASSES)), device=device)
            labels[torch.arange(len(known_indices), device=device), yk[known_indices]] = 1
            loss = F.binary_cross_entropy_with_logits(model(batch), labels,
                pos_weight=torch.full((len(CLASSES),), config['positive_weight'], device=device))
            optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
            losses.append(float(loss.detach()))
        model.eval()
        cks, cus = base.predict(model, ck, device, temp), base.predict(model, cu, device, temp)
        threshold = base.select_threshold(cks, cus)
        cal = base.summarize(ck, cu, cks, cus, threshold)
        metric = cal['known_correct_accept_rate']
        if metric > best_metric:
            best_metric = metric
            save({'model': model.state_dict(), 'config': config, 'epoch': epoch,
                'threshold': threshold, 'calibration': cal}, best_path)
        save({'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
            'config': config, 'epoch': epoch, 'best_metric': best_metric,
            'rng_torch': torch.get_rng_state(), 'rng_numpy': np.random.get_state(),
            'rng_python': random.getstate(), 'rng_cuda': torch.cuda.get_rng_state_all()
            if device.type == 'cuda' else []}, last_path)
        print(f'epoch {epoch+1} loss={np.mean(losses):.4f} '
              f'cal_known={metric:.4f} cal_unknown={cal["unknown_false_accept_count"]}',
              flush=True)
    best = torch.load(best_path, map_location='cpu', weights_only=False)
    model.load_state_dict(best['model']); model.eval()
    result = {'best_epoch': best['epoch']+1, 'threshold': best['threshold'],
        'calibration': best['calibration'],
        'unseen': base.summarize(rk, ru, base.predict(model, rk, device, temp),
            base.predict(model, ru, device, temp), best['threshold']),
        'unknown_calibration_ids': id_groups[0], 'unknown_evaluation_ids': id_groups[1],
        'unknown_counts': counts, 'test_used': False,
        'previously_inspected_validation': True}
    (OUT / 'validation-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print('best', result['best_epoch'], 'unseen', result['unseen'], flush=True)


if __name__ == '__main__':
    main()
