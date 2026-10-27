"""Combine normalized PIM combiner and ResNet layer4 features, without test."""
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'model/runs/recognition/pim_multilayer_raw_20261027'
OUT = ROOT / 'model/runs/recognition/pim_multilayer_features_20261027'
LAYER4_WEIGHT = .5


def normalize(x):
    x = x.astype(np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(min=1e-6)


def main():
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    if not manifest.get('development_only') or not manifest.get('extra_layer4') or \
            manifest.get('unknown_train_ids') == 'all':
        raise ValueError('Source must be development-only with disjoint unknown IDs')
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('train-known', 'train-unknown', 'validation-known', 'validation-unknown'):
        with np.load(SOURCE / f'{name}.npz') as stored:
            data = {key: stored[key].copy() for key in stored.files}
        if data['features'].shape[0] != data['backbone_features'].shape[0]:
            raise ValueError(f'Layer mismatch in {name}')
        features = np.concatenate((normalize(data['features']),
            LAYER4_WEIGHT * normalize(data['backbone_features'])), axis=1)
        data.pop('backbone_features')
        data['features'] = features
        target = OUT / f'{name}.npz'
        temporary = target.with_suffix('.tmp')
        with temporary.open('wb') as handle:
            np.savez_compressed(handle, **data)
        os.replace(temporary, target)
        print(f'{name}: {features.shape}', flush=True)
    (OUT / 'manifest.json').write_text(json.dumps({'source': str(SOURCE.relative_to(ROOT)),
        'feature_dim': int(features.shape[1]), 'layer4_weight': LAYER4_WEIGHT,
        'unknown_train_ids': manifest['unknown_train_ids'], 'test_used': False},
        indent=2) + '\n')


if __name__ == '__main__':
    main()
