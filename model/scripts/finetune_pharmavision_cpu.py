"""CPU fine-tune of EfficientNetV2-S final blocks on original PharmaVision split.

No test data is opened. Checkpoints include optimizer, scheduler and RNG at each
completed epoch. Resume always begins at the next epoch with its saved LR.
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
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'data/processed/pharmavision/manifest.csv'
WEIGHTS = ROOT / 'model/checkpoints/efficientnet_v2_s_imagenet1k_v1.pth'
RUNS = ROOT / 'model/runs/defect'
CONFIG = {'epochs': 20, 'patience': 6, 'batch_size': 8, 'image_size': 224,
          'learning_rate': 1e-4, 'weight_decay': 1e-4, 'val_threshold': 0.40,
          'trainable_feature_blocks': [6, 7], 'seed': 20261027,
          'augmentation': 'horizontal/vertical flips, rotation 12 degrees, brightness/contrast 7%',
          'selection': 'validation defective F2 then recall then precision at fixed threshold'}


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


def atomic_save(path, value):
    tmp = path.with_suffix('.tmp.pt')
    torch.save(value, tmp)
    os.replace(tmp, path)


class Images(Dataset):
    def __init__(self, split, image_size):
        with MANIFEST.open(newline='') as f:
            self.rows = [r for r in csv.DictReader(f) if r['split'] == split]
        expected = 380 if split == 'train' else 60
        if len(self.rows) != expected:
            raise ValueError(f'{split}: expected {expected}, got {len(self.rows)}')
        counts = {label: sum(r['label'] == label for r in self.rows) for label in ('normal', 'defective')}
        if counts != {'normal': expected // 2, 'defective': expected // 2}:
            raise ValueError(f'{split}: unexpected class counts {counts}')
        norm = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        if split == 'train':
            self.transform = transforms.Compose([
                transforms.Resize((image_size, image_size)),
                transforms.RandomHorizontalFlip(), transforms.RandomVerticalFlip(),
                transforms.RandomRotation(12),
                transforms.ColorJitter(brightness=.07, contrast=.07),
                transforms.ToTensor(), norm])
        else:
            self.transform = transforms.Compose([
                transforms.Resize(image_size), transforms.CenterCrop(image_size),
                transforms.ToTensor(), norm])

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(ROOT / row['image_path']) as image:
            image = ImageOps.exif_transpose(image).convert('RGB')
            return self.transform(image), int(row['label'] == 'defective')


def model_for_training():
    model = models.efficientnet_v2_s(weights=None)
    model.load_state_dict(torch.load(WEIGHTS, map_location='cpu', weights_only=True))
    model.classifier[1] = torch.nn.Linear(model.classifier[1].in_features, 2)
    for parameter in model.features.parameters():
        parameter.requires_grad = False
    for index in CONFIG['trainable_feature_blocks']:
        for parameter in model.features[index].parameters():
            parameter.requires_grad = True
    return model


def freeze_early_batchnorm(model):
    for index, block in enumerate(model.features):
        if index not in CONFIG['trainable_feature_blocks']:
            block.eval()


def score(model, loader):
    model.eval()
    values = torch.zeros(4, dtype=torch.long)  # TN FP FN TP
    loss_sum = 0.0
    with torch.inference_mode():
        for images, target in loader:
            logits = model(images)
            loss_sum += float(torch.nn.functional.cross_entropy(logits, target, reduction='sum'))
            probability = logits.softmax(dim=1)[:, 1]
            prediction = (probability >= CONFIG['val_threshold']).long()
            values[0] += ((target == 0) & (prediction == 0)).sum()
            values[1] += ((target == 0) & (prediction == 1)).sum()
            values[2] += ((target == 1) & (prediction == 0)).sum()
            values[3] += ((target == 1) & (prediction == 1)).sum()
    tn, fp, fn, tp = (int(v) for v in values)
    recall = tp / (tp + fn) if tp + fn else 0
    precision = tp / (tp + fp) if tp + fp else 0
    f2 = 5 * tp / (5 * tp + 4 * fn + fp) if 5 * tp + 4 * fn + fp else 0
    return {'validation_loss': loss_sum / len(loader.dataset), 'defective_recall': recall,
            'defective_precision': precision, 'defective_f2': f2,
            'confusion_matrix_rows_normal_defective': [[tn, fp], [fn, tp]]}


def rank(metric):
    return (metric['defective_f2'], metric['defective_recall'], metric['defective_precision'])


def main():
    p = argparse.ArgumentParser()
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--run-name')
    group.add_argument('--resume')
    p.add_argument('--threads', type=int, default=8)
    args = p.parse_args()
    if args.threads < 1:
        raise ValueError('threads must be positive')
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    if args.run_name:
        if not args.run_name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-' for c in args.run_name):
            raise ValueError('invalid run name')
        run = RUNS / args.run_name
        if run.exists():
            raise FileExistsError(run)
        run.mkdir(parents=True)
        manifest = {'status': 'running', 'config': CONFIG,
                    'dataset_sha256': digest(MANIFEST), 'imagenet_weights_sha256': digest(WEIGHTS),
                    'device': 'cpu', 'test_used': False}
        atomic_json(run / 'run-manifest.json', manifest)
    else:
        run = Path(args.resume).resolve()
        if run.parent != RUNS.resolve():
            raise ValueError('resume directory must be under model/runs/defect')
        manifest = json.loads((run / 'run-manifest.json').read_text())
        if manifest['config'] != CONFIG or manifest['dataset_sha256'] != digest(MANIFEST) or manifest['imagenet_weights_sha256'] != digest(WEIGHTS):
            raise ValueError('resume config, dataset or initial weights changed')
        if manifest['status'] == 'completed':
            raise ValueError('run already completed')
        pid_path = run / 'pid'
        if pid_path.exists():
            pid = int(pid_path.read_text())
            try:
                cmd = Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
                if 'finetune_pharmavision_cpu.py' in cmd and str(run) in cmd:
                    raise RuntimeError(f'run already active: PID {pid}')
            except FileNotFoundError:
                pass
    (run / 'pid').write_text(str(os.getpid()))
    try:
        random.seed(CONFIG['seed']); np.random.seed(CONFIG['seed']); torch.manual_seed(CONFIG['seed'])
        train_set = Images('train', CONFIG['image_size'])
        val_set = Images('validation', CONFIG['image_size'])
        val_loader = DataLoader(val_set, batch_size=CONFIG['batch_size'], num_workers=0)
        model = model_for_training()
        optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),
                                      lr=CONFIG['learning_rate'], weight_decay=CONFIG['weight_decay'])
        # Epoch-boundary schedule; checkpoint LR must equal scheduler's last LR.
        scheduler = torch.optim.lr_scheduler.LambdaLR(
            optimizer, lr_lambda=lambda step: 0.1 if step == 0 else
            0.5 * (1 + math.cos(math.pi * (step - 1) / max(1, CONFIG['epochs'] - 1))))
        start, best, bad = 0, None, 0
        if args.resume:
            ckpt = torch.load(run / 'last.pt', map_location='cpu', weights_only=False)
            if ckpt['config'] != CONFIG:
                raise ValueError('checkpoint config mismatch')
            model.load_state_dict(ckpt['model'])
            optimizer.load_state_dict(ckpt['optimizer'])
            scheduler.load_state_dict(ckpt['scheduler'])
            if abs(optimizer.param_groups[0]['lr'] - scheduler.get_last_lr()[0]) > 1e-12:
                raise ValueError('optimizer/scheduler learning-rate mismatch')
            random.setstate(ckpt['rng_python'])
            np.random.set_state(ckpt['rng_numpy'])
            torch.set_rng_state(ckpt['rng_torch'])
            start, best, bad = ckpt['epoch'] + 1, ckpt['best'], ckpt['bad_epochs']
            print(f'resume epoch {start+1}, LR {optimizer.param_groups[0]["lr"]:.9g}', flush=True)
        for epoch in range(start, CONFIG['epochs']):
            generator = torch.Generator().manual_seed(CONFIG['seed'] + epoch)
            train_loader = DataLoader(train_set, batch_size=CONFIG['batch_size'], shuffle=True,
                                      generator=generator, num_workers=0)
            model.train(); freeze_early_batchnorm(model)
            total = 0.0
            lr_used = optimizer.param_groups[0]['lr']
            for images, target in train_loader:
                optimizer.zero_grad(set_to_none=True)
                logits = model(images)
                loss = torch.nn.functional.cross_entropy(logits, target)
                loss.backward()
                optimizer.step()
                total += float(loss.detach()) * len(target)
            metric = score(model, val_loader)
            improved = best is None or rank(metric) > rank(best)
            if improved:
                best, bad = metric, 0
            else:
                bad += 1
            scheduler.step()
            ckpt = {'epoch': epoch, 'config': CONFIG, 'model': model.state_dict(),
                    'optimizer': optimizer.state_dict(), 'scheduler': scheduler.state_dict(),
                    'rng_python': random.getstate(), 'rng_numpy': np.random.get_state(),
                    'rng_torch': torch.get_rng_state(), 'best': best, 'bad_epochs': bad}
            atomic_save(run / 'last.pt', ckpt)
            if improved:
                atomic_save(run / 'best.pt', ckpt)
            record = {'epoch': epoch + 1, 'learning_rate_used': lr_used,
                      'learning_rate_next': optimizer.param_groups[0]['lr'],
                      'train_loss': total / len(train_set), **metric, 'best_f2': best['defective_f2'],
                      'improved': improved}
            with (run / 'metrics.jsonl').open('a') as f:
                f.write(json.dumps(record) + '\n')
            print(json.dumps(record), flush=True)
            if bad >= CONFIG['patience']:
                print('early stopping: validation F2 has not improved', flush=True)
                break
        manifest['status'] = 'completed'
        manifest['best_validation'] = best
        manifest['best_epoch'] = next(json.loads(line)['epoch'] for line in (run / 'metrics.jsonl').read_text().splitlines()
                                      if json.loads(line)['improved'] and json.loads(line)['defective_f2'] == best['defective_f2']
                                      and json.loads(line)['defective_recall'] == best['defective_recall']
                                      and json.loads(line)['defective_precision'] == best['defective_precision'])
        atomic_json(run / 'run-manifest.json', manifest)
    finally:
        (run / 'pid').unlink(missing_ok=True)


if __name__ == '__main__':
    main()
