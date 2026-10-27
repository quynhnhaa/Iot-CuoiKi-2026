"""Validate that a YOLOv7 last.pt can resume at the saved epoch and LR."""
import argparse
import json
import math
import sys
from pathlib import Path

import torch
import yaml


def expected_lr_factor(epoch: int, epochs: int, final_factor: float, linear: bool) -> float:
    if linear:
        return (1 - epoch / (epochs - 1)) * (1 - final_factor) + final_factor
    return (1 + math.cos(math.pi * epoch / epochs)) / 2 * (1 - final_factor) + final_factor


def inspect(run_dir: Path) -> dict:
    run_dir = Path(run_dir).resolve()
    options_path = run_dir / 'opt.yaml'
    hyp_path = run_dir / 'hyp.yaml'
    checkpoint_path = run_dir / 'weights/last.pt'
    for path in (options_path, hyp_path, checkpoint_path):
        if not path.is_file():
            raise ValueError(f'Missing resume file: {path}')
    options = yaml.safe_load(options_path.read_text())
    hyp = yaml.safe_load(hyp_path.read_text())
    # YOLOv7's trusted local checkpoint contains a pickled model object.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/yolov7'))
    checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
    if not isinstance(checkpoint, dict):
        raise ValueError('Checkpoint is not a YOLOv7 training dictionary')
    epoch = checkpoint.get('epoch')
    total_epochs = options.get('epochs')
    if type(epoch) is not int or type(total_epochs) is not int or not 0 <= epoch < total_epochs - 1:
        raise ValueError(f'No remaining epoch to resume: saved={epoch}, total={total_epochs}')
    optimizer = checkpoint.get('optimizer')
    if not isinstance(optimizer, dict) or not optimizer.get('param_groups') or not optimizer.get('state'):
        raise ValueError('Checkpoint lacks optimizer state; stripped/final weights cannot resume')
    if checkpoint.get('model') is None or checkpoint.get('ema') is None:
        raise ValueError('Checkpoint lacks model or EMA state')
    if type(options.get('total_batch_size')) is not int or options['total_batch_size'] < 1:
        raise ValueError('Missing original total_batch_size in opt.yaml')
    factor = expected_lr_factor(epoch, total_epochs, float(hyp['lrf']), bool(options['linear_lr']))
    learning_rates = []
    for index, group in enumerate(optimizer['param_groups']):
        initial_lr = group.get('initial_lr')
        actual_lr = group.get('lr')
        expected_lr = initial_lr * factor if initial_lr is not None else None
        if expected_lr is None or actual_lr is None or not math.isclose(actual_lr, expected_lr, rel_tol=1e-5, abs_tol=1e-8):
            raise ValueError(f'Optimizer group {index} LR mismatch: actual={actual_lr}, expected={expected_lr}')
        learning_rates.append(actual_lr)
    if not (Path(options['data']).is_file() and Path(options['save_dir']).resolve() == run_dir):
        raise ValueError('Saved dataset path or save directory no longer matches this run')
    return {'run_dir': str(run_dir), 'checkpoint': str(checkpoint_path), 'saved_epoch_zero_based': epoch, 'next_epoch_zero_based': epoch + 1, 'total_epochs': total_epochs, 'total_batch_size': options['total_batch_size'], 'workers': options['workers'], 'image_size': options['img_size'], 'learning_rates': learning_rates, 'optimizer_state_entries': len(optimizer['state']), 'ema_updates': checkpoint.get('updates')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.run_dir), indent=2))
