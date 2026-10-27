"""Train YOLO11s on the audited, group-separated VAIPE one-class dataset.

The run directory is immutable on first start. Resume uses Ultralytics last.pt,
which restores optimizer, scheduler, epoch, and data configuration.
"""
import argparse
import hashlib
import json
from pathlib import Path

import torch
from ultralytics import YOLO
import ultralytics

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/processed/vaipe/yolov7/pill.yaml'
WEIGHTS = ROOT / 'model/checkpoints/yolo11s.pt'
PROJECT = ROOT / 'model/runs/detector'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', default='yolo11s_pill_20261027')
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--device', choices=['auto', 'cuda', 'cpu'], default='auto')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    run = PROJECT / args.name
    device = 0 if (args.device == 'cuda' or args.device == 'auto' and torch.cuda.is_available()) else 'cpu'
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable')
    if not DATA.is_file() or not WEIGHTS.is_file():
        raise FileNotFoundError('Export VAIPE pill.yaml and download yolo11s.pt first')
    sources = {str(path.relative_to(ROOT)): sha256(path) for path in [
        DATA, WEIGHTS, ROOT / 'data/processed/vaipe/splits/train.csv',
        ROOT / 'data/processed/vaipe/splits/validation.csv']}
    config = {'name': args.name, 'model': 'YOLO11s pretrained detection',
        'epochs': args.epochs, 'imgsz': 640, 'batch': args.batch,
        'workers': args.workers, 'seed': 20261027, 'device_at_start': str(device),
        'ultralytics': ultralytics.__version__, 'torch': torch.__version__,
        'source_sha256': sources, 'smoke': args.smoke,
        'test_used_for_selection': False}
    manifest = run / 'run-manifest.json'
    if args.resume:
        if not manifest.is_file() or not (run / 'weights/last.pt').is_file():
            raise FileNotFoundError('Resume requires run-manifest.json and weights/last.pt')
        previous = json.loads(manifest.read_text())
        for key in ['model', 'epochs', 'imgsz', 'batch', 'workers', 'seed',
                    'ultralytics', 'source_sha256', 'smoke']:
            if previous[key] != config[key]:
                raise ValueError(f'Resume mismatch: {key}')
        model = YOLO(str(run / 'weights/last.pt'))
        model.train(resume=True, device=device)
    else:
        if run.exists():
            raise FileExistsError(run)
        run.mkdir(parents=True)
        manifest.write_text(json.dumps(config, indent=2) + '\n')
        model = YOLO(str(WEIGHTS))
        # Ultralytics creates the run directory. Validation selects best.pt;
        # the held-out test set is evaluated only after this run finishes.
        model.train(data=str(DATA), epochs=args.epochs, imgsz=640,
            batch=args.batch, workers=args.workers, device=device,
            project=str(PROJECT), name=args.name, exist_ok=True,
            seed=20261027, deterministic=True, pretrained=True,
            amp=True, patience=0, save=True, save_period=1,
            plots=False, verbose=False, fraction=.02 if args.smoke else 1.0)


if __name__ == '__main__':
    main()
