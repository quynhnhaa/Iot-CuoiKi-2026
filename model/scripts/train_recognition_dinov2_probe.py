"""Train-only seven-class linear probe on frozen DINOv2 features; no test."""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from train_recognition_pim import CLASSES

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'model/runs/recognition/dinov2_vits14_features_20261027'
OUT = ROOT / 'model/runs/recognition/dinov2_probe_20261027'


def load(name):
    with np.load(SOURCE / f'{name}.npz') as handle:
        return {key: handle[key].copy() for key in handle.files}


def norm(features):
    x = torch.as_tensor(features, dtype=torch.float32)
    return F.normalize(x, dim=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', choices=['auto', 'cuda', 'cpu'], default='auto')
    args = parser.parse_args()
    device_name = ('cuda' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else args.device
    if device_name == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable')
    device = torch.device(device_name)
    torch.manual_seed(20261027)
    train = load('train-known')
    x = norm(train['features']).to(device)
    y = torch.tensor([CLASSES.index(int(value)) for value in train['class_ids']], device=device)
    pools = [torch.where(y == index)[0] for index in range(len(CLASSES))]
    head = torch.nn.Linear(x.shape[1], len(CLASSES)).to(device)
    optimizer = torch.optim.AdamW(head.parameters(), lr=.001, weight_decay=.001)
    for epoch in range(100):
        for _ in range(40):
            indices = torch.cat([pool[torch.randint(len(pool), (16,), device=device)]
                                 for pool in pools])
            loss = F.cross_entropy(head(x[indices]), y[indices])
            optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
        if (epoch+1) % 20 == 0:
            print(f'epoch {epoch+1} loss={float(loss.detach()):.4f}', flush=True)
    head.eval()
    OUT.mkdir(parents=True, exist_ok=True)
    torch.save({'model': head.cpu().state_dict(), 'epochs': 100,
        'classes': CLASSES, 'source': str(SOURCE.relative_to(ROOT)),
        'test_used': False}, OUT / 'linear-probe.pt')
    head.to(device)
    for name in ('train-known', 'train-unknown', 'validation-known', 'validation-unknown'):
        data = load(name)
        with torch.inference_mode():
            logits = torch.cat([head(chunk.to(device)).cpu() for chunk in
                norm(data['features']).split(1024)]).numpy()
        data['logits'] = logits
        target = OUT / f'{name}.npz'
        temp = target.with_suffix('.tmp')
        with temp.open('wb') as handle:
            np.savez_compressed(handle, **data)
        os.replace(temp, target)
    validation = load('validation-known')
    with np.load(OUT / 'validation-known.npz') as handle:
        prediction = handle['logits'].argmax(1)
    truth = np.array([CLASSES.index(int(value)) for value in validation['class_ids']])
    per_class = {}
    for index, cls in enumerate(CLASSES):
        tp = ((prediction == index) & (truth == index)).sum()
        fp = ((prediction == index) & (truth != index)).sum()
        fn = ((prediction != index) & (truth == index)).sum()
        per_class[str(cls)] = float(2*tp/(2*tp+fp+fn))
    result = {'validation_accuracy': float((prediction == truth).mean()),
        'validation_macro_f1': float(np.mean(list(per_class.values()))),
        'validation_per_class_f1': per_class, 'test_used': False}
    (OUT / 'validation-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
