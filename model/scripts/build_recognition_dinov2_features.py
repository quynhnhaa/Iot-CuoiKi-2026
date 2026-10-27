"""Join frozen DINOv2 and PIM ROI embeddings with strict row alignment."""
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PIM = ROOT / 'model/runs/recognition/open_set_features_20261026'
DINO = ROOT / 'model/runs/recognition/dinov2_vits14_features_20261027'
OUT = ROOT / 'model/runs/recognition/pim_dinov2_features_20261027'
DINO_WEIGHT = .5


def normalized(x):
    x = x.astype(np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(min=1e-6)


def main():
    manifest = json.loads((DINO / 'manifest.json').read_text())
    if manifest['test_used'] or not manifest['unknown_train_ids']:
        raise ValueError('DINOv2 development features required')
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('train-known', 'train-unknown', 'validation-known', 'validation-unknown'):
        with np.load(PIM / f'{name}.npz') as handle:
            pim = {key: handle[key].copy() for key in handle.files}
        with np.load(DINO / f'{name}.npz') as handle:
            dino = {key: handle[key].copy() for key in handle.files}
        if name == 'train-unknown':
            mask = np.isin(pim['class_ids'], manifest['unknown_train_ids'])
            pim = {key: value[mask] for key, value in pim.items()}
        for key in ('class_ids', 'image_ids', 'annotation_indices'):
            if not np.array_equal(pim[key], dino[key]):
                raise ValueError(f'{name}: {key} mismatch')
        pim['features'] = np.concatenate([normalized(pim['features']),
            DINO_WEIGHT*normalized(dino['features'])], axis=1).astype(np.float32)
        target = OUT / f'{name}.npz'
        temporary = target.with_suffix('.tmp')
        with temporary.open('wb') as handle:
            np.savez_compressed(handle, **pim)
        os.replace(temporary, target)
        print(name, pim['features'].shape, flush=True)
    (OUT / 'manifest.json').write_text(json.dumps({'pim_source': str(PIM.relative_to(ROOT)),
        'dinov2_source': str(DINO.relative_to(ROOT)), 'dinov2_weight': DINO_WEIGHT,
        'feature_dim': int(pim['features'].shape[1]),
        'unknown_train_ids': manifest['unknown_train_ids'], 'test_used': False},
        indent=2) + '\n')


if __name__ == '__main__':
    main()
