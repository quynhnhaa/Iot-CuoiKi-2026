"""Join PIM, ResNet layer4 mean and spatial std; train/validation only."""
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'model/runs/recognition/pim_spatial_raw_20261027'
OUT = ROOT / 'model/runs/recognition/pim_spatial_features_20261027'


def unit(x):
    x = x.astype(np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(min=1e-6)


def main():
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    if not manifest['development_only'] or not manifest['extra_layer4_std']:
        raise ValueError('Spatial train/validation source required')
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('train-known', 'train-unknown', 'validation-known', 'validation-unknown'):
        with np.load(SOURCE / f'{name}.npz') as handle:
            data = {key: handle[key].copy() for key in handle.files}
        data['features'] = np.concatenate([unit(data['features']),
            .5*unit(data.pop('backbone_features')),
            .5*unit(data.pop('backbone_std_features'))], axis=1).astype(np.float32)
        target = OUT / f'{name}.npz'
        temp = target.with_suffix('.tmp')
        with temp.open('wb') as handle:
            np.savez_compressed(handle, **data)
        os.replace(temp, target)
        print(name, data['features'].shape, flush=True)
    (OUT / 'manifest.json').write_text(json.dumps({'source': str(SOURCE.relative_to(ROOT)),
        'feature_dim': int(data['features'].shape[1]), 'weights': [1., .5, .5],
        'test_used': False, 'unknown_train_ids': manifest['unknown_train_ids']},
        indent=2) + '\n')


if __name__ == '__main__':
    main()
