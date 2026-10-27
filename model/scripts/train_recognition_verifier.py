"""Train seven class-conditioned verification heads on frozen FGVC-PIM features.

Unknown training IDs are disjoint from every unknown validation ID. Threshold and
best epoch use only group-hashed calibration data; VAIPE test is never loaded.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from benchmark_recognition_open_set import CLASSES, normalized_features, temperature
from extract_recognition_features import ROOT, ROI, UNKNOWN

OUT = ROOT / 'model/runs/recognition/class_conditioned_verifier_20261027'
FEATURE_DIR = ROOT / 'model/runs/recognition/open_set_features_20261026'
SEED = 20261027


def load(split, kind):
    with np.load(FEATURE_DIR / f'{split}-{kind}.npz') as data:
        return {key: data[key].copy() for key in data.files}


def grouped_mask(split, kind, parity):
    source = (ROI if kind == 'known' else UNKNOWN) / f'{split}.csv'
    with source.open(newline='') as handle:
        groups = [row['group_id'] for row in csv.DictReader(handle)]
    return np.array([int(hashlib.sha256(group.encode()).hexdigest(), 16) % 2 == parity
                     for group in groups], dtype=bool)


def subset(data, mask):
    return {key: value[mask] for key, value in data.items()}


class Verifier(torch.nn.Module):
    def __init__(self, input_dim=256):
        super().__init__()
        self.layers = torch.nn.Sequential(torch.nn.Linear(input_dim, 256), torch.nn.ReLU(),
            torch.nn.Dropout(.15), torch.nn.Linear(256, len(CLASSES)))

    def forward(self, features):
        return self.layers(features)


def predict(model, data, device, calibrated_temperature):
    features = normalized_features(data)
    with torch.inference_mode():
        verification = torch.cat([model(batch.to(device)).sigmoid().cpu()
                                  for batch in features.split(1024)]).numpy()
    classifier = F.softmax(torch.as_tensor(data['logits'], dtype=torch.float32) /
                           calibrated_temperature, dim=1).numpy()
    prediction = classifier.argmax(1)
    rows = np.arange(len(prediction))
    class_probability = classifier[rows, prediction]
    verifier_probability = verification[rows, prediction]
    score = class_probability * verifier_probability
    return score, prediction, class_probability, verifier_probability


def select_threshold(known, unknown, target_far=.01):
    known_score, known_prediction = known[:2]
    unknown_score = unknown[0]
    true = np.array([CLASSES.index(int(value)) for value in CALIBRATION_KNOWN['class_ids']])
    best = None
    for threshold in np.unique(np.r_[known_score, unknown_score]):
        far = float(np.mean(unknown_score >= threshold))
        if far > target_far:
            continue
        correct = float(np.mean((known_score >= threshold) & (known_prediction == true)))
        wrong = float(np.mean((known_score >= threshold) & (known_prediction != true)))
        key = (correct, -wrong, -far)
        if best is None or key > best[0]:
            best = (key, float(threshold))
    if best is None:
        raise RuntimeError('No threshold satisfies validation unknown FAR')
    return best[1]


def summarize(known_data, unknown_data, known, unknown, threshold):
    known_score, known_prediction = known[:2]
    unknown_score = unknown[0]
    true = np.array([CLASSES.index(int(value)) for value in known_data['class_ids']])
    accepted = known_score >= threshold
    accepted_unknown = unknown_score >= threshold
    per_class = {}
    for index, class_id in enumerate(CLASSES):
        mask = true == index
        count = int((mask & accepted & (known_prediction == true)).sum())
        per_class[str(class_id)] = {'correct_accepted': count, 'total': int(mask.sum())}
    return {'known_correct_accept_rate': float(np.mean(accepted & (known_prediction == true))),
            'known_wrong_accept_rate': float(np.mean(accepted & (known_prediction != true))),
            'unknown_false_accept_rate': float(np.mean(accepted_unknown)),
            'unknown_false_accept_count': int(accepted_unknown.sum()),
            'known_count': len(known_score), 'unknown_count': len(unknown_score),
            'per_class': per_class}


def per_class_thresholds(calibration_known, calibration_unknown, known, unknown):
    known_score, known_prediction = known[:2]
    unknown_score, unknown_prediction = unknown[:2]
    true = np.array([CLASSES.index(int(value)) for value in calibration_known['class_ids']])
    thresholds = []
    negative_counts = []
    for index in range(len(CLASSES)):
        positive = (known_prediction == index) & (true == index)
        negative = unknown_prediction == index
        negative_counts.append(int(negative.sum()))
        if not positive.any() or negative.sum() < 20:
            thresholds.append(float('inf'))
            continue
        best = None
        for candidate in np.unique(np.r_[known_score[positive], unknown_score[negative]]):
            far = np.mean(unknown_score[negative] >= candidate)
            if far > .01:
                continue
            recall = np.mean(known_score[positive] >= candidate)
            key = (recall, -far)
            if best is None or key > best[0]:
                best = (key, float(candidate))
        thresholds.append(best[1])
    return np.array(thresholds), negative_counts


def summarize_per_class(known_data, unknown_data, known, unknown, thresholds):
    known_score, known_prediction = known[:2]
    unknown_score, unknown_prediction = unknown[:2]
    true = np.array([CLASSES.index(int(value)) for value in known_data['class_ids']])
    known_accepted = known_score >= thresholds[known_prediction]
    unknown_accepted = unknown_score >= thresholds[unknown_prediction]
    per_class = {}
    for index, class_id in enumerate(CLASSES):
        mask = true == index
        per_class[str(class_id)] = {
            'correct_accepted': int((mask & known_accepted & (known_prediction == true)).sum()),
            'total': int(mask.sum())}
    return {'known_correct_accept_rate': float(np.mean(known_accepted & (known_prediction == true))),
            'known_wrong_accept_rate': float(np.mean(known_accepted & (known_prediction != true))),
            'unknown_false_accept_rate': float(np.mean(unknown_accepted)),
            'unknown_false_accept_count': int(unknown_accepted.sum()),
            'known_count': len(known_score), 'unknown_count': len(unknown_score),
            'per_class': per_class}


def atomic_save(payload, path):
    temporary = path.with_suffix('.tmp')
    torch.save(payload, temporary)
    os.replace(temporary, path)


def main():
    global OUT, FEATURE_DIR, CALIBRATION_KNOWN
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--device', choices=('auto', 'cuda', 'cpu'), default='auto')
    parser.add_argument('--feature-dir', type=str, default=str(FEATURE_DIR))
    parser.add_argument('--run-name', type=str, default=OUT.name)
    args = parser.parse_args()
    if not all(character.isalnum() or character in '._-' for character in args.run_name):
        raise ValueError('Invalid run name')
    OUT = ROOT / 'model/runs/recognition' / args.run_name
    FEATURE_DIR = Path(args.feature_dir).resolve()
    device_name = ('cuda' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else args.device
    if device_name == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable')
    device = torch.device(device_name)
    known_train = load('train', 'known')
    unknown_train = load('train', 'unknown')
    known_validation = load('validation', 'known')
    unknown_validation = load('validation', 'unknown')
    negative_ids = sorted(set(unknown_train['class_ids'].tolist()) -
                          set(unknown_validation['class_ids'].tolist()))
    unknown_train = subset(unknown_train, np.isin(unknown_train['class_ids'], negative_ids))
    if len(unknown_train['class_ids']) < 100:
        raise ValueError('Too few class-disjoint unknown training samples')
    known_calibration_mask = grouped_mask('validation', 'known', 0)
    unknown_calibration_mask = grouped_mask('validation', 'unknown', 0)
    if len(known_calibration_mask) != len(known_validation['class_ids']):
        raise ValueError('Known feature rows differ from ROI manifest')
    if len(unknown_calibration_mask) != len(unknown_validation['class_ids']):
        raise ValueError('Unknown feature rows differ from ROI manifest')
    CALIBRATION_KNOWN = subset(known_validation, known_calibration_mask)
    calibration_unknown = subset(unknown_validation, unknown_calibration_mask)
    holdout_known = subset(known_validation, ~known_calibration_mask)
    holdout_unknown = subset(unknown_validation, ~unknown_calibration_mask)
    calibrated_temperature = temperature(CALIBRATION_KNOWN['logits'],
                                         CALIBRATION_KNOWN['class_ids'])

    known_features = normalized_features(known_train).to(device)
    negative_features = normalized_features(unknown_train).to(device)
    true_indices = torch.tensor([CLASSES.index(int(value)) for value in known_train['class_ids']],
                                device=device)
    pools = [torch.where(true_indices == index)[0] for index in range(len(CLASSES))]
    data_hash = hashlib.sha256(known_features.cpu().numpy().tobytes() +
                               negative_features.cpu().numpy().tobytes() +
                               known_train['class_ids'].tobytes() +
                               np.asarray(negative_ids, dtype=np.int32).tobytes()).hexdigest()
    config = {'epochs': args.epochs, 'seed': SEED, 'negative_train_ids': negative_ids,
              'negative_train_count': len(negative_features), 'known_train_count': len(known_features),
              'data_hash': data_hash, 'learning_rate': .0003, 'steps_per_epoch': 80,
              'known_per_class_per_step': 16, 'negative_per_step': 112,
              'positive_weight': 6.0, 'device': device_name,
              'feature_dir': str(FEATURE_DIR), 'feature_dim': known_features.shape[1]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'run-manifest.json').write_text(json.dumps(config, indent=2) + '\n')
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    if device.type == 'cuda':
        torch.cuda.manual_seed_all(SEED)
    model = Verifier(config['feature_dim']).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config['learning_rate'], weight_decay=.001)
    last_path, best_path = OUT / 'last.pt', OUT / 'best.pt'
    start, best_metric = 0, -1.0
    if last_path.exists():
        saved = torch.load(last_path, map_location='cpu', weights_only=False)
        if saved['config'] != config:
            raise ValueError('Checkpoint config/data mismatch')
        model.load_state_dict(saved['model']); optimizer.load_state_dict(saved['optimizer'])
        torch.set_rng_state(saved['rng_torch'])
        np.random.set_state(saved['rng_numpy']); random.setstate(saved['rng_python'])
        if device.type == 'cuda':
            torch.cuda.set_rng_state_all(saved['rng_cuda'])
        start, best_metric = saved['epoch'] + 1, saved['best_metric']
        print(f'Resuming epoch {start + 1}/{args.epochs}', flush=True)
    for epoch in range(start, args.epochs):
        model.train(); losses = []
        for _ in range(config['steps_per_epoch']):
            indices = torch.cat([pool[torch.randint(len(pool),
                (config['known_per_class_per_step'],), device=device)] for pool in pools])
            negative_indices = torch.randint(len(negative_features),
                (config['negative_per_step'],), device=device)
            batch = torch.cat([known_features[indices], negative_features[negative_indices]])
            labels = torch.zeros((len(batch), len(CLASSES)), device=device)
            labels[torch.arange(len(indices), device=device), true_indices[indices]] = 1
            logits = model(batch)
            loss = F.binary_cross_entropy_with_logits(logits, labels,
                pos_weight=torch.full((len(CLASSES),), config['positive_weight'], device=device))
            optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
            losses.append(float(loss.detach()))
        model.eval()
        calibration_known_signals = predict(model, CALIBRATION_KNOWN, device, calibrated_temperature)
        calibration_unknown_signals = predict(model, calibration_unknown, device, calibrated_temperature)
        threshold = select_threshold(calibration_known_signals, calibration_unknown_signals)
        calibration_result = summarize(CALIBRATION_KNOWN, calibration_unknown,
                                       calibration_known_signals, calibration_unknown_signals, threshold)
        metric = calibration_result['known_correct_accept_rate']
        if metric > best_metric:
            best_metric = metric
            atomic_save({'model': model.state_dict(), 'epoch': epoch,
                         'calibration_result': calibration_result, 'threshold': threshold,
                         'config': config}, best_path)
        checkpoint = {'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
                      'epoch': epoch, 'best_metric': best_metric, 'config': config,
                      'rng_torch': torch.get_rng_state(),
                      'rng_numpy': np.random.get_state(), 'rng_python': random.getstate(),
                      'rng_cuda': torch.cuda.get_rng_state_all() if device.type == 'cuda' else []}
        atomic_save(checkpoint, last_path)
        print(f'epoch {epoch + 1}/{args.epochs} loss={np.mean(losses):.4f} '
              f'calibration correct={metric:.4f} unknown FAR='
              f'{calibration_result["unknown_false_accept_rate"]:.4f}', flush=True)
    best = torch.load(best_path, map_location='cpu', weights_only=False)
    model.load_state_dict(best['model']); model.eval()
    threshold = best['threshold']
    holdout_known_signals = predict(model, holdout_known, device, calibrated_temperature)
    holdout_unknown_signals = predict(model, holdout_unknown, device, calibrated_temperature)
    calibration_known_signals = predict(model, CALIBRATION_KNOWN, device, calibrated_temperature)
    calibration_unknown_signals = predict(model, calibration_unknown, device, calibrated_temperature)
    class_thresholds, negative_counts = per_class_thresholds(CALIBRATION_KNOWN,
        calibration_unknown, calibration_known_signals, calibration_unknown_signals)
    result = {'best_epoch': best['epoch'] + 1, 'threshold': threshold,
              'temperature': calibrated_temperature, 'negative_train_ids': negative_ids,
              'calibration': best['calibration_result'],
              'heldout_validation': summarize(holdout_known, holdout_unknown,
                holdout_known_signals, holdout_unknown_signals, threshold),
              'per_class_policy_exploratory': {
                'thresholds_by_id': {str(class_id): float(value)
                    for class_id, value in zip(CLASSES, class_thresholds)},
                'calibration_unknown_predicted_counts': {str(class_id): count
                    for class_id, count in zip(CLASSES, negative_counts)},
                'heldout_validation': summarize_per_class(holdout_known, holdout_unknown,
                    holdout_known_signals, holdout_unknown_signals, class_thresholds)},
              'test_used': False, 'split_rule': 'SHA-256 group_id parity; 0 calibration, 1 holdout'}
    (OUT / 'validation-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
