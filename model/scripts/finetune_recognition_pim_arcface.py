"""Fine-tune the seven-class PIM checkpoint with balanced sampling and ArcFace.

Checkpoints include optimizer, scheduler, AMP scaler and RNG for exact epoch resume.
The old test split is not read. This is an experimental validation-only run.
"""
import argparse
import fcntl
import json
import math
import os
import random
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, WeightedRandomSampler

from train_recognition_pim import (ROOT, ROI, RUNS, CLASSES, CLASS_TO_INDEX,
    ROIDataset, build_model, pim_loss, save_atomic, sha, validate)

PARENT = RUNS / 'pim_resnet50_7class_20261026_v2' / 'best.pt'
RUN = RUNS / 'pim_arcface_balanced_20261027'
CONFIG = {'epochs': 6, 'batch_size': 4, 'accumulation': 2,
          'image_size': 320, 'workers': 4, 'learning_rate': 2e-5,
          'weight_decay': .0005, 'arcface_margin': .2,
          'arcface_scale': 16.0, 'arcface_weight': .25,
          'seed': 20261027, 'classes': CLASSES}


def arcface_loss(features, classifier_weight, labels, config):
    cosine = F.linear(F.normalize(features.float(), dim=1),
                      F.normalize(classifier_weight.float(), dim=1)).float().clamp(-1 + 1e-6, 1 - 1e-6)
    target = cosine.gather(1, labels[:, None])
    margin = config['arcface_margin']
    margin_cosine = target * math.cos(margin) - torch.sqrt(1 - target.square()) * math.sin(margin)
    margin_logits = cosine.scatter(1, labels[:, None], margin_cosine)
    return F.cross_entropy(margin_logits * config['arcface_scale'], labels)


def main():
    global RUN
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--device', choices=('auto', 'cuda', 'cpu'), default='auto')
    parser.add_argument('--run-name', default=RUN.name)
    args = parser.parse_args()
    if not all(character.isalnum() or character in '._-' for character in args.run_name):
        raise ValueError('Invalid run name')
    RUN = RUNS / args.run_name
    device_name = ('cuda' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else args.device
    if device_name == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable')
    device = torch.device(device_name)
    train_set = ROIDataset('train', CONFIG['image_size'])
    validation_set = ROIDataset('validation', CONFIG['image_size'])
    counts = Counter(int(row['class_id']) for row in train_set.rows)
    if set(counts) != set(CLASSES):
        raise ValueError('Missing recognition class in train split')
    weights = torch.tensor([1 / counts[int(row['class_id'])] for row in train_set.rows], dtype=torch.double)
    sampler = WeightedRandomSampler(weights, num_samples=len(train_set), replacement=True)
    train_loader = DataLoader(train_set, batch_size=CONFIG['batch_size'], sampler=sampler,
        num_workers=CONFIG['workers'], pin_memory=device.type == 'cuda')
    validation_loader = DataLoader(validation_set, batch_size=CONFIG['batch_size'], shuffle=False,
        num_workers=CONFIG['workers'], pin_memory=device.type == 'cuda')
    source = torch.load(PARENT, map_location='cpu', weights_only=False)
    base_config = source['config']
    model = build_model(base_config, load_imagenet=False).to(device)
    model.load_state_dict(source['model'])
    features = []
    hook = model.combiner.dropout.register_forward_hook(
        lambda _module, _inputs, output: features.append(output.flatten(1)))
    optimizer = torch.optim.AdamW(model.parameters(), lr=CONFIG['learning_rate'],
                                   weight_decay=CONFIG['weight_decay'])
    updates_per_epoch = math.ceil(len(train_loader) / CONFIG['accumulation'])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=CONFIG['epochs'] * updates_per_epoch)
    scaler = torch.amp.GradScaler('cuda', enabled=device.type == 'cuda')
    random.seed(CONFIG['seed']); np.random.seed(CONFIG['seed']); torch.manual_seed(CONFIG['seed'])
    if device.type == 'cuda':
        torch.cuda.manual_seed_all(CONFIG['seed'])
    hashes = {'parent_checkpoint': sha(PARENT),
              'train_manifest': sha(ROI / 'train.csv'),
              'validation_manifest': sha(ROI / 'validation.csv')}
    if args.resume:
        if not RUN.is_dir():
            raise FileNotFoundError(RUN)
    else:
        RUN.mkdir(parents=True, exist_ok=False)
    lock = (RUN / 'run.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(f'Run is already active: {RUN}') from exc
    manifest_path = RUN / 'run-manifest.json'
    start, best = 0, -1.0
    if args.resume:
        manifest = json.loads(manifest_path.read_text())
        if manifest['config'] != CONFIG or manifest['input_sha256'] != hashes:
            raise ValueError('Fine-tune config or input data changed')
        if manifest['device'] != device_name:
            raise ValueError('Exact resume requires the same device; start a new CPU run instead')
        saved = torch.load(RUN / 'last.pt', map_location='cpu', weights_only=False)
        if saved['config'] != CONFIG:
            raise ValueError('Checkpoint config changed')
        model.load_state_dict(saved['model'])
        optimizer.load_state_dict(saved['optimizer'])
        scheduler.load_state_dict(saved['scheduler'])
        scaler.load_state_dict(saved['scaler'])
        if abs(optimizer.param_groups[0]['lr'] - scheduler.get_last_lr()[0]) > 1e-12:
            raise ValueError('Optimizer/scheduler learning-rate mismatch')
        random.setstate(saved['rng_python']); np.random.set_state(saved['rng_numpy'])
        torch.set_rng_state(saved['rng_torch'])
        if device.type == 'cuda':
            torch.cuda.set_rng_state_all(saved['rng_cuda'])
        start, best = saved['epoch'] + 1, saved['best_macro_f1']
        if start >= CONFIG['epochs']:
            raise ValueError('Run is already complete')
        print(f'Resuming epoch {start + 1}/{CONFIG["epochs"]}, '
              f'LR={optimizer.param_groups[0]["lr"]:.9g}', flush=True)
    else:
        manifest = {'status': 'running', 'config': CONFIG, 'input_sha256': hashes,
                    'parent_epoch': source['epoch'] + 1, 'device': device_name,
                    'train_samples': len(train_set), 'validation_samples': len(validation_set),
                    'train_class_counts': dict(sorted(counts.items()))}
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    for epoch in range(start, CONFIG['epochs']):
        model.train(); optimizer.zero_grad(set_to_none=True); total = 0.0
        for batch, (images, labels) in enumerate(train_loader):
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            features.clear()
            with torch.autocast(device_type='cuda', enabled=device.type == 'cuda'):
                outputs = model(images)
                if len(features) != 1:
                    raise RuntimeError('PIM combiner feature hook did not fire once')
                original = pim_loss(outputs, labels, base_config['loss_weights'])
                angular = arcface_loss(features[0], model.combiner.classifier.weight,
                                       labels, CONFIG)
                loss = (original + CONFIG['arcface_weight'] * angular) / CONFIG['accumulation']
            scaler.scale(loss).backward()
            if (batch + 1) % CONFIG['accumulation'] == 0 or batch + 1 == len(train_loader):
                previous = scaler.get_scale()
                scaler.step(optimizer); scaler.update()
                if scaler.get_scale() >= previous:
                    scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            total += float(loss.detach()) * CONFIG['accumulation']
            if (batch + 1) % 250 == 0:
                print(f'epoch {epoch + 1}/{CONFIG["epochs"]} '
                      f'batch {batch + 1}/{len(train_loader)} '
                      f'loss={total / (batch + 1):.4f}', flush=True)
        features.clear()
        metric = validate(model, validation_loader, device)
        improved = metric['macro_f1'] > best
        if improved:
            best = metric['macro_f1']
        checkpoint = {'epoch': epoch, 'config': CONFIG, 'model_config': base_config,
                      'model': model.state_dict(),
                      'optimizer': optimizer.state_dict(), 'scheduler': scheduler.state_dict(),
                      'scaler': scaler.state_dict(), 'best_macro_f1': best,
                      'rng_python': random.getstate(), 'rng_numpy': np.random.get_state(),
                      'rng_torch': torch.get_rng_state(),
                      'rng_cuda': torch.cuda.get_rng_state_all() if device.type == 'cuda' else []}
        save_atomic(checkpoint, RUN / 'last.pt')
        if improved:
            save_atomic(checkpoint, RUN / 'best.pt')
        record = {'epoch': epoch + 1, 'train_loss': total / len(train_loader),
                  'lr': optimizer.param_groups[0]['lr'], **metric, 'best_macro_f1': best}
        with (RUN / 'metrics.jsonl').open('a') as handle:
            handle.write(json.dumps(record) + '\n')
        print(f'epoch {epoch + 1} macro_F1={metric["macro_f1"]:.4f} '
              f'accuracy={metric["accuracy"]:.4f} best={best:.4f}', flush=True)
    hook.remove()
    manifest = json.loads(manifest_path.read_text())
    manifest['status'] = 'completed'; manifest['best_macro_f1'] = best
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
