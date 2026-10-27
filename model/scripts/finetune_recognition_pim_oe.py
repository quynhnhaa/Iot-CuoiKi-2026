"""Fine-tune PIM with class-disjoint outlier exposure and epoch resume.

Known images keep the original PIM loss. Unknown training images encourage
uniform combiner logits. This run uses no VAIPE test images or labels.
"""
import argparse
import csv
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
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms

from train_recognition_pim import (ROOT, ROI, RUNS, CLASSES, ROIDataset,
    build_model, pim_loss, save_atomic, sha, validate)
from extract_recognition_features import UNKNOWN

PARENT = RUNS / 'pim_resnet50_7class_20261026_v2' / 'best.pt'
RUN = RUNS / 'pim_oe_20261027'
CONFIG = {'epochs': 4, 'steps_per_epoch': 200, 'known_batch': 2, 'unknown_batch': 2,
    'image_size': 320, 'workers': 4, 'learning_rate': 8e-6,
    'weight_decay': .0005, 'oe_weight': .5, 'seed': 20261027,
    'classes': CLASSES}


class UnknownDataset(Dataset):
    def __init__(self, allowed):
        with (UNKNOWN / 'train.csv').open(newline='') as handle:
            self.rows = [row for row in csv.DictReader(handle)
                         if int(row['class_id']) in allowed]
        self.transform = transforms.Compose([transforms.Resize((360, 360)),
            transforms.RandomCrop(320), transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=.12, contrast=.12, saturation=.08),
            transforms.ToTensor(),
            transforms.Normalize([.485, .456, .406], [.229, .224, .225])])

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(ROOT / row['image_path']) as raw:
            image = ImageOps.exif_transpose(raw).convert('RGB')
            box = tuple(int(row[f'crop_{side}']) for side in
                        ('left', 'top', 'right', 'bottom'))
            image = image.crop(box)
        return self.transform(image)


def main():
    global RUN
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--run-name', default=RUN.name)
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    args = parser.parse_args()
    if not all(c.isalnum() or c in '._-' for c in args.run_name):
        raise ValueError('Invalid run name')
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable')
    RUN = RUNS / args.run_name
    with (UNKNOWN / 'validation.csv').open(newline='') as handle:
        validation_ids = {int(row['class_id']) for row in csv.DictReader(handle)}
    with (UNKNOWN / 'train.csv').open(newline='') as handle:
        train_ids = {int(row['class_id']) for row in csv.DictReader(handle)}
    allowed = train_ids - validation_ids
    if len(allowed) < 20:
        raise ValueError('Too few class-disjoint unknown IDs')
    known_set = ROIDataset('train', CONFIG['image_size'])
    unknown_set = UnknownDataset(allowed)
    validation_set = ROIDataset('validation', CONFIG['image_size'])
    counts = Counter(int(row['class_id']) for row in known_set.rows)
    weights = torch.tensor([1/counts[int(row['class_id'])] for row in known_set.rows],
                           dtype=torch.double)
    known_sampler = WeightedRandomSampler(weights,
        num_samples=CONFIG['epochs']*CONFIG['steps_per_epoch']*CONFIG['known_batch'],
        replacement=True)
    unknown_sampler = torch.utils.data.RandomSampler(unknown_set, replacement=True,
        num_samples=CONFIG['epochs']*CONFIG['steps_per_epoch']*CONFIG['unknown_batch'])
    known_loader = DataLoader(known_set, batch_size=CONFIG['known_batch'],
        sampler=known_sampler, num_workers=CONFIG['workers'], pin_memory=True)
    unknown_loader = DataLoader(unknown_set, batch_size=CONFIG['unknown_batch'],
        sampler=unknown_sampler, num_workers=CONFIG['workers'], pin_memory=True)
    validation_loader = DataLoader(validation_set, batch_size=4, shuffle=False,
        num_workers=CONFIG['workers'], pin_memory=True)
    parent = torch.load(PARENT, map_location='cpu', weights_only=False)
    model_config = parent['config']
    device = torch.device(args.device)
    model = build_model(model_config, load_imagenet=False).to(device)
    model.load_state_dict(parent['model'])
    optimizer = torch.optim.AdamW(model.parameters(), lr=CONFIG['learning_rate'],
                                   weight_decay=CONFIG['weight_decay'])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,
        T_max=CONFIG['epochs']*CONFIG['steps_per_epoch'])
    scaler = torch.amp.GradScaler('cuda', enabled=device.type == 'cuda')
    random.seed(CONFIG['seed']); np.random.seed(CONFIG['seed']); torch.manual_seed(CONFIG['seed'])
    if device.type == 'cuda':
        torch.cuda.manual_seed_all(CONFIG['seed'])
    hashes = {'parent': sha(PARENT), 'train_known': sha(ROI / 'train.csv'),
        'validation_known': sha(ROI / 'validation.csv'),
        'train_unknown': sha(UNKNOWN / 'train.csv'),
        'validation_unknown': sha(UNKNOWN / 'validation.csv')}
    if args.resume:
        if not RUN.is_dir():
            raise FileNotFoundError(RUN)
    else:
        RUN.mkdir(parents=True, exist_ok=False)
    lock = (RUN / 'run.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(f'Run already active: {RUN}') from exc
    manifest_path = RUN / 'run-manifest.json'
    start, best = 0, -1.0
    if args.resume:
        manifest = json.loads(manifest_path.read_text())
        if manifest['config'] != CONFIG or manifest['input_sha256'] != hashes or \
                manifest['unknown_train_ids'] != sorted(allowed) or \
                manifest['device'] != args.device:
            raise ValueError('Configuration, device or input changed')
        saved = torch.load(RUN / 'last.pt', map_location='cpu', weights_only=False)
        model.load_state_dict(saved['model'])
        optimizer.load_state_dict(saved['optimizer']); scheduler.load_state_dict(saved['scheduler'])
        scaler.load_state_dict(saved['scaler'])
        if abs(optimizer.param_groups[0]['lr'] - scheduler.get_last_lr()[0]) > 1e-12:
            raise ValueError('Optimizer/scheduler LR mismatch')
        random.setstate(saved['rng_python']); np.random.set_state(saved['rng_numpy'])
        torch.set_rng_state(saved['rng_torch'])
        if device.type == 'cuda':
            torch.cuda.set_rng_state_all(saved['rng_cuda'])
        start, best = saved['epoch']+1, saved['best_macro_f1']
        print(f'Resuming epoch {start+1}/{CONFIG["epochs"]} '
              f'LR={optimizer.param_groups[0]["lr"]:.9g}', flush=True)
    else:
        manifest_path.write_text(json.dumps({'status': 'running', 'config': CONFIG,
            'input_sha256': hashes, 'unknown_train_ids': sorted(allowed),
            'unknown_train_count': len(unknown_set), 'device': args.device,
            'test_used': False}, indent=2) + '\n')
    # Restore the epoch and LR exactly. DataLoader worker augmentations and sampled
    # image order may differ after a restart; this is epoch resume, not bitwise replay.
    known_iter, unknown_iter = iter(known_loader), iter(unknown_loader)
    for _ in range(start * CONFIG['steps_per_epoch']):
        next(known_iter); next(unknown_iter)
    for epoch in range(start, CONFIG['epochs']):
        model.train(); total = 0.0
        for step in range(CONFIG['steps_per_epoch']):
            known_images, known_labels = next(known_iter)
            unknown_images = next(unknown_iter)
            known_images = known_images.to(device, non_blocking=True)
            known_labels = known_labels.to(device, non_blocking=True)
            unknown_images = unknown_images.to(device, non_blocking=True)
            with torch.autocast(device_type='cuda', enabled=device.type == 'cuda'):
                outputs = model(torch.cat([known_images, unknown_images]))
                known_outputs = {name: value[:len(known_images)] for name, value in outputs.items()}
                known_loss = pim_loss(known_outputs, known_labels, model_config['loss_weights'])
                unknown_logits = outputs['comb_outs'][len(known_images):].float()
                oe_loss = torch.logsumexp(unknown_logits, dim=1).mean() - \
                    unknown_logits.mean(dim=1).mean() - math.log(len(CLASSES))
                loss = known_loss + CONFIG['oe_weight'] * oe_loss
            optimizer.zero_grad(set_to_none=True)
            previous = scaler.get_scale()
            scaler.scale(loss).backward(); scaler.step(optimizer); scaler.update()
            if scaler.get_scale() >= previous:
                scheduler.step()
            total += float(loss.detach())
            if (step+1) % 50 == 0:
                print(f'epoch {epoch+1}/{CONFIG["epochs"]} step {step+1}/'
                      f'{CONFIG["steps_per_epoch"]} loss={total/(step+1):.4f}', flush=True)
        metric = validate(model, validation_loader, device)
        improved = metric['macro_f1'] > best
        if improved:
            best = metric['macro_f1']
        checkpoint = {'epoch': epoch, 'config': CONFIG, 'model_config': model_config,
            'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
            'scheduler': scheduler.state_dict(), 'scaler': scaler.state_dict(),
            'best_macro_f1': best, 'rng_python': random.getstate(),
            'rng_numpy': np.random.get_state(), 'rng_torch': torch.get_rng_state(),
            'rng_cuda': torch.cuda.get_rng_state_all() if device.type == 'cuda' else []}
        save_atomic(checkpoint, RUN / 'last.pt')
        if improved:
            save_atomic(checkpoint, RUN / 'best.pt')
        with (RUN / 'metrics.jsonl').open('a') as handle:
            handle.write(json.dumps({'epoch': epoch+1, 'train_loss': total/CONFIG['steps_per_epoch'],
                'lr': optimizer.param_groups[0]['lr'], **metric}) + '\n')
        print(f'epoch {epoch+1} macro_F1={metric["macro_f1"]:.4f} '
              f'best={best:.4f}', flush=True)
    manifest = json.loads(manifest_path.read_text())
    manifest['status'] = 'completed'; manifest['best_macro_f1'] = best
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
