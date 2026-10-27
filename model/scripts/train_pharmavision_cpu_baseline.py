"""CPU baseline for PharmaVision with resumable ResNet-50 feature extraction.

The original dataset partitions are never changed. Validation alone selects the
regularization and decision threshold; test is evaluated only by --evaluate-test.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'data/processed/pharmavision/manifest.csv'
WEIGHTS = {
    'resnet50': ROOT / 'model/checkpoints/resnet50_imagenet1k_v1.pth',
    'efficientnet_v2_s': ROOT / 'model/checkpoints/efficientnet_v2_s_imagenet1k_v1.pth',
}
RUNS = ROOT / 'model/runs/defect'
SEED = 20261027


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(tmp, path)


def atomic_npz(path, **values):
    tmp = path.with_suffix('.tmp.npz')
    np.savez_compressed(tmp, **values)
    os.replace(tmp, path)


def read_rows():
    with MANIFEST.open(newline='') as f:
        rows = list(csv.DictReader(f))
    expected = {'train': {'normal': 190, 'defective': 190},
                'validation': {'normal': 30, 'defective': 30},
                'test': {'normal': 100, 'defective': 100}}
    for split, labels in expected.items():
        for label, count in labels.items():
            selected = [r for r in rows if r['split'] == split and r['label'] == label]
            if len(selected) != count:
                raise ValueError(f'{split}/{label}: expected {count}, got {len(selected)}')
            if any(r['is_readable'] != 'True' or not (ROOT / r['image_path']).is_file() for r in selected):
                raise ValueError(f'{split}/{label}: missing or unreadable image')
    if len(rows) != 640 or len({r['sha256'] for r in rows}) != 640:
        raise ValueError('manifest count or duplicate SHA-256 mismatch')
    return rows


def build_model(backbone):
    model = models.resnet50(weights=None) if backbone == 'resnet50' else models.efficientnet_v2_s(weights=None)
    state = torch.load(WEIGHTS[backbone], map_location='cpu', weights_only=True)
    model.load_state_dict(state)
    if backbone == 'resnet50':
        model.fc = torch.nn.Identity()
        dimension = 2048
    else:
        model.classifier = torch.nn.Identity()
        dimension = 1280
    model.eval()
    return model, dimension


def extract(run, split, rows, model, batch_size, dimension, backbone):
    path = run / f'{split}-features.npz'
    selected = [r for r in rows if r['split'] == split]
    paths = np.asarray([r['image_path'] for r in selected])
    labels = np.asarray([int(r['label'] == 'defective') for r in selected], dtype=np.int64)
    if path.exists():
        with np.load(path) as saved:
            features = saved['features'].copy()
            prior_paths = saved['paths'].copy()
            prior_labels = saved['labels'].copy()
        if not np.array_equal(prior_paths, paths[:len(prior_paths)]) or not np.array_equal(prior_labels, labels[:len(prior_labels)]):
            raise ValueError(f'{split} feature cache does not match manifest')
        if features.ndim != 2 or features.shape != (len(prior_paths), dimension):
            raise ValueError(f'{split} invalid feature cache shape')
    else:
        features = np.empty((0, dimension), dtype=np.float32)
    if len(features) == len(selected):
        return features, labels
    size = 384 if backbone == 'efficientnet_v2_s' else 224
    resize = 384 if backbone == 'efficientnet_v2_s' else 256
    transform = transforms.Compose([
        transforms.Resize(resize), transforms.CenterCrop(size), transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    chunks = [features]
    for start in range(len(features), len(selected), batch_size):
        batch = selected[start:start + batch_size]
        images = []
        for row in batch:
            with Image.open(ROOT / row['image_path']) as image:
                images.append(transform(ImageOps.exif_transpose(image).convert('RGB')))
        with torch.inference_mode():
            output = model(torch.stack(images)).numpy().astype(np.float32)
        chunks.append(output)
        features = np.concatenate(chunks)
        atomic_npz(path, features=features, paths=paths[:len(features)], labels=labels[:len(features)])
        print(f'{split}: {len(features)}/{len(selected)}', flush=True)
    return features, labels


def metrics(y, probabilities, threshold):
    pred = (probabilities >= threshold).astype(int)
    tn = int(np.sum((y == 0) & (pred == 0)))
    fp = int(np.sum((y == 0) & (pred == 1)))
    fn = int(np.sum((y == 1) & (pred == 0)))
    tp = int(np.sum((y == 1) & (pred == 1)))
    recall = tp / (tp + fn) if tp + fn else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    f2 = 5 * tp / (5 * tp + 4 * fn + fp) if 5 * tp + 4 * fn + fp else 0.0
    return {'threshold': float(threshold), 'defective_recall': recall,
            'defective_precision': precision, 'defective_f2': f2,
            'confusion_matrix_rows_normal_defective': [[tn, fp], [fn, tp]],
            'false_normal_defective_count': fn}


def fit_logistic(train_x, train_y, c):
    # Standardize using training data only; a frozen backbone keeps CPU cost low.
    mean = train_x.mean(axis=0).astype(np.float32)
    std = np.maximum(train_x.std(axis=0), 1e-5).astype(np.float32)
    x = torch.from_numpy((train_x - mean) / std)
    y = torch.from_numpy(train_y.astype(np.float32))
    weight = torch.nn.Parameter(torch.zeros(x.shape[1]))
    bias = torch.nn.Parameter(torch.zeros(()))
    optimizer = torch.optim.LBFGS([weight, bias], lr=1.0, max_iter=120,
                                  tolerance_grad=1e-7, tolerance_change=1e-9)

    def closure():
        optimizer.zero_grad()
        logits = x @ weight + bias
        loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, y)
        loss = loss + (0.5 / (c * len(y))) * weight.square().sum()
        loss.backward()
        return loss

    optimizer.step(closure)
    return mean, std, weight.detach().numpy().copy(), float(bias.detach())


def predict_logistic(x, clf):
    mean, std, weight, bias = clf
    logits = ((x - mean) / std) @ weight + bias
    return 1 / (1 + np.exp(-np.clip(logits, -80, 80)))


def choose_threshold(y, probabilities):
    # Candidate boundaries change predictions only at observed validation scores.
    candidates = np.unique(np.concatenate(([0.0, 1.0], probabilities)))
    scored = [(metrics(y, probabilities, t), t) for t in candidates]
    # F2 first, then recall, then precision; higher threshold breaks exact ties.
    return max(scored, key=lambda item: (item[0]['defective_f2'],
                                         item[0]['defective_recall'],
                                         item[0]['defective_precision'], item[1]))[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-name', default='resnet50_frozen_cpu_20261027')
    p.add_argument('--evaluate-test', action='store_true')
    p.add_argument('--batch-size', type=int, default=16)
    p.add_argument('--threads', type=int, default=8)
    p.add_argument('--backbone', choices=['resnet50', 'efficientnet_v2_s'], default='resnet50')
    args = p.parse_args()
    if not args.run_name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-' for c in args.run_name):
        raise ValueError('invalid run name')
    if args.batch_size < 1 or args.threads < 1:
        raise ValueError('batch size and threads must be positive')
    torch.set_num_threads(args.threads)
    run = RUNS / args.run_name
    run.mkdir(parents=True, exist_ok=True)
    rows = read_rows()
    resize = 384 if args.backbone == 'efficientnet_v2_s' else 256
    crop = 384 if args.backbone == 'efficientnet_v2_s' else 224
    model_name = ('torchvision resnet50 ImageNet1K V1 frozen features + logistic regression'
                  if args.backbone == 'resnet50' else
                  'torchvision efficientnet_v2_s ImageNet1K V1 frozen features + logistic regression')
    config = {'model': model_name,
              'seed': SEED, 'manifest_sha256': digest(MANIFEST), 'weights_sha256': digest(WEIGHTS[args.backbone]),
              'preprocess': f'EXIF transpose, RGB, resize short side {resize}, center crop {crop}, ImageNet normalize',
              'device': 'cpu', 'classes': ['normal', 'defective']}
    config_path = run / 'config.json'
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise ValueError('run configuration or source files changed; cannot resume')
    atomic_json(config_path, config)
    model, dimension = build_model(args.backbone)
    train_x, train_y = extract(run, 'train', rows, model, args.batch_size, dimension, args.backbone)
    val_x, val_y = extract(run, 'validation', rows, model, args.batch_size, dimension, args.backbone)
    candidates = []
    for c in (0.01, 0.1, 1.0, 10.0):
        clf = fit_logistic(train_x, train_y, c)
        probabilities = predict_logistic(val_x, clf)
        threshold = choose_threshold(val_y, probabilities)
        candidates.append((metrics(val_y, probabilities, threshold), c, clf))
    best, c, clf = max(candidates, key=lambda item: (item[0]['defective_f2'],
                                                     item[0]['defective_recall'],
                                                     item[0]['defective_precision'], -item[1]))
    result = {'config': config, 'selected_C': c, 'selection': 'validation defective F2, recall, precision',
              'validation': best, 'candidate_validation': [dict(C=cand_c, **score) for score, cand_c, _ in candidates],
              'classifier': {'mean': clf[0].tolist(), 'std': clf[1].tolist(),
                             'weight': clf[2].tolist(), 'bias': clf[3]}}
    result_path = run / 'result.json'
    if result_path.exists():
        previous = json.loads(result_path.read_text())
        if previous['selected_C'] != c or previous['validation'] != best:
            raise ValueError('existing validation result differs; refusing to overwrite')
        if 'test' in previous:
            result['test'] = previous['test']
    if args.evaluate_test and 'test' not in result:
        test_x, test_y = extract(run, 'test', rows, model, args.batch_size, dimension, args.backbone)
        test_prob = predict_logistic(test_x, clf)
        result['test'] = metrics(test_y, test_prob, best['threshold'])
    atomic_json(result_path, result)
    print(json.dumps({k: v for k, v in result.items() if k in ('selected_C', 'validation', 'test')}, indent=2), flush=True)


if __name__ == '__main__':
    main()
