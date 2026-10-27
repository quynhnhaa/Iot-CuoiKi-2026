"""Add CPU color descriptors to frozen PIM features for a validation-only study.

Color normalization is fitted on known train and class-disjoint unknown train.
The script never reads VAIPE test or GPU state.
"""
import argparse
import csv
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from train_recognition_pim import ROOT, ROI
from extract_recognition_features import UNKNOWN

BASE = ROOT / 'model/runs/recognition/open_set_features_20261026'
OUT = ROOT / 'model/runs/recognition/pim_color_features_20261027'
WEIGHT = .75


def descriptor(item):
    kind, row = item
    image_path = ROOT / (row['crop_path'] if kind == 'known' else row['image_path'])
    with Image.open(image_path) as raw:
        image = (ImageOps.exif_transpose(raw).convert('RGB') if kind == 'unknown'
                 else raw.convert('RGB'))
        if kind == 'unknown':
            box = tuple(int(row[f'crop_{key}']) for key in ('left', 'top', 'right', 'bottom'))
            image = image.crop(box)
        image = image.resize((64, 64), Image.Resampling.BILINEAR)
    rgb = np.asarray(image, dtype=np.float32) / 255
    hsv = np.asarray(image.convert('HSV'), dtype=np.float32) / 255
    yy, xx = np.ogrid[:64, :64]
    mask = ((xx - 31.5) / 28)**2 + ((yy - 31.5) / 28)**2 <= 1
    pixels = rgb[mask]
    hue, saturation, value = (hsv[mask, index] for index in range(3))
    hue_hist = np.histogram(hue, bins=16, range=(0, 1), weights=saturation)[0]
    sat_hist = np.histogram(saturation, bins=8, range=(0, 1))[0]
    val_hist = np.histogram(value, bins=8, range=(0, 1))[0]
    joint = np.histogram2d(hue, saturation, bins=(8, 4), range=((0, 1), (0, 1)))[0]
    parts = [hue_hist.astype(np.float32), sat_hist.astype(np.float32),
             val_hist.astype(np.float32), joint.flatten().astype(np.float32),
             pixels.mean(axis=0), pixels.std(axis=0)]
    for part in parts[:4]:
        part /= max(float(part.sum()), 1e-6)
    return np.concatenate(parts).astype(np.float32)


def read_source(split, kind, allowed_ids):
    with np.load(BASE / f'{split}-{kind}.npz') as stored:
        features = {key: stored[key].copy() for key in stored.files}
    path = (ROI if kind == 'known' else UNKNOWN) / f'{split}.csv'
    with path.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    if split == 'train' and kind == 'unknown':
        mask = np.isin(features['class_ids'], list(allowed_ids))
        features = {key: value[mask] for key, value in features.items()}
        rows = [row for row in rows if int(row['class_id']) in allowed_ids]
    if len(rows) != len(features['class_ids']):
        raise ValueError(f'{split}-{kind}: feature count and ROI manifest differ')
    for index, row in enumerate(rows):
        if (row['image_id'] != features['image_ids'][index] or
                int(row['annotation_index']) != int(features['annotation_indices'][index]) or
                int(row['class_id']) != int(features['class_ids'][index])):
            raise ValueError(f'{split}-{kind}: identity mismatch at row {index}')
    return features, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError('workers must be positive')
    with (UNKNOWN / 'validation.csv').open(newline='') as handle:
        validation_ids = {int(row['class_id']) for row in csv.DictReader(handle)}
    with (UNKNOWN / 'train.csv').open(newline='') as handle:
        train_ids = {int(row['class_id']) for row in csv.DictReader(handle)}
    allowed_ids = train_ids - validation_ids
    if not allowed_ids:
        raise ValueError('No class-disjoint unknown training IDs')
    OUT.mkdir(parents=True, exist_ok=True)
    collected = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for split, kind in [('train', 'known'), ('train', 'unknown'),
                            ('validation', 'known'), ('validation', 'unknown')]:
            data, rows = read_source(split, kind, allowed_ids)
            color = np.stack(list(pool.map(descriptor,
                ((kind, row) for row in rows), chunksize=16)))
            collected[(split, kind)] = (data, color)
            print(f'{split}-{kind}: {len(rows)} crops, {color.shape[1]} color features', flush=True)
    training_color = np.concatenate([collected[('train', 'known')][1],
                                     collected[('train', 'unknown')][1]])
    mean = training_color.mean(axis=0)
    std = training_color.std(axis=0).clip(min=1e-4)
    np.savez_compressed(OUT / 'train-color-normalization.npz', mean=mean, std=std)
    for (split, kind), (data, color) in collected.items():
        pill = data['features'].astype(np.float32)
        pill /= np.linalg.norm(pill, axis=1, keepdims=True).clip(min=1e-6)
        color = np.clip((color - mean) / std, -5, 5)
        color /= np.linalg.norm(color, axis=1, keepdims=True).clip(min=1e-6)
        features = np.concatenate([pill, WEIGHT * color], axis=1).astype(np.float32)
        destination = OUT / f'{split}-{kind}.npz'
        temporary = destination.with_suffix('.tmp')
        with temporary.open('wb') as handle:
            np.savez_compressed(handle, features=features, logits=data['logits'],
                class_ids=data['class_ids'], image_ids=data['image_ids'],
                annotation_indices=data['annotation_indices'])
        os.replace(temporary, destination)
    (OUT / 'manifest.json').write_text(json.dumps({
        'source_feature_dir': str(BASE.relative_to(ROOT)),
        'feature_dim': int(features.shape[1]),
        'descriptor': '64px central ellipse HSV hue/saturation/value histograms and RGB moments',
        'color_weight': WEIGHT, 'normalization_source': 'train known + class-disjoint train unknown',
        'unknown_train_ids': sorted(allowed_ids), 'test_used': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
