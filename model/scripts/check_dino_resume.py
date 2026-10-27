"""Reject DINO resume with incompatible settings or incomplete checkpoint."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import torch


def check(run: Path, device: str) -> dict:
    run = run.resolve()
    root = Path(__file__).resolve().parents[2]
    if run.parent != root / 'model/runs/detector':
        raise ValueError('Run must be directly under model/runs/detector')
    m = json.loads((run / 'run-manifest.json').read_text())
    cfg = Path(m['config'])
    if hashlib.sha256(cfg.read_bytes()).hexdigest() != m['config_sha256']:
        raise ValueError('Config changed since launch')
    if device != m['device']:
        raise ValueError('Device change requires explicit review; resume keeps original device')
    pid_path = run / 'pid'
    if pid_path.exists():
        pid = pid_path.read_text().strip()
        if pid.isdigit():
            p = subprocess.run(['ps', '-p', pid, '-o', 'args='], capture_output=True, text=True)
            if 'main.py' in p.stdout and str(run) in p.stdout:
                raise ValueError(f'DINO already running with PID {pid}')
    ckpt = torch.load(run / 'checkpoint.pth', map_location='cpu', weights_only=False)
    for key in ('model', 'optimizer', 'lr_scheduler', 'epoch', 'args'):
        if key not in ckpt:
            raise ValueError(f'Checkpoint missing {key}')
    saved = ckpt['args']
    for key, value in [('batch_size',m['batch_size']),('epochs',m['epochs']),('seed',m['seed'])]:
        if getattr(saved,key) != value:
            raise ValueError(f'Checkpoint {key} mismatch')
    next_epoch = ckpt['epoch'] + 1
    if not 0 < next_epoch < m['epochs']:
        raise ValueError('No epochs left to resume')
    if len(ckpt['optimizer']['param_groups']) != len(ckpt['lr_scheduler']['_last_lr']):
        raise ValueError('Optimizer/scheduler parameter groups differ')
    for group, lr in zip(ckpt['optimizer']['param_groups'],ckpt['lr_scheduler']['_last_lr']):
        if abs(group['lr']-lr)>1e-10:
            raise ValueError('Optimizer/scheduler learning rate mismatch')
    return {'next_epoch_one_based':next_epoch+1,'lr':ckpt['lr_scheduler']['_last_lr']}


if __name__ == '__main__':
    try: print(json.dumps(check(Path(sys.argv[1]),sys.argv[2]),indent=2))
    except Exception as exc:
        print(f'Resume rejected: {exc}',file=sys.stderr);sys.exit(1)
