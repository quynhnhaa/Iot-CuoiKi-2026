"""Extract official frozen DINOv2 ViT-S/14 ROI features; train/validation only."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from torchvision import transforms

from extract_recognition_features import ROOT, ROI, UNKNOWN, FeatureDataset

SOURCE_DEFAULT = Path.home() / '.cache/torch/hub/facebookresearch_dinov2_main'
WEIGHTS_DEFAULT = ROOT / 'model/.cache/torch/hub/checkpoints/dinov2_vits14_pretrain.pth'
OUT_DEFAULT = ROOT / 'model/runs/recognition/dinov2_vits14_features_20261027'


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=SOURCE_DEFAULT)
    parser.add_argument('--weights', type=Path, default=WEIGHTS_DEFAULT)
    parser.add_argument('--output-dir', type=Path, default=OUT_DEFAULT)
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable')
    if not args.source.is_dir() or not args.weights.is_file():
        raise FileNotFoundError('DINOv2 source or official weights missing')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    weight_hash = sha(args.weights)
    prior = output / 'manifest.json'
    if prior.exists() and json.loads(prior.read_text())['weights_sha256'] != weight_hash:
        raise ValueError('Output belongs to different DINOv2 weights')
    model = torch.hub.load(str(args.source), 'dinov2_vits14', source='local',
                           pretrained=False)
    model.load_state_dict(torch.load(args.weights, map_location='cpu', weights_only=True))
    device = torch.device(args.device)
    model = model.to(device).eval()
    with (UNKNOWN / 'validation.csv').open(newline='') as handle:
        import csv
        validation_ids = {int(row['class_id']) for row in csv.DictReader(handle)}
    with (UNKNOWN / 'train.csv').open(newline='') as handle:
        train_ids = {int(row['class_id']) for row in csv.DictReader(handle)}
    allowed = train_ids - validation_ids
    if not allowed:
        raise ValueError('No class-disjoint unknown training IDs')
    transform = transforms.Compose([transforms.Resize((256, 256)),
        transforms.CenterCrop(224), transforms.ToTensor(),
        transforms.Normalize([.485, .456, .406], [.229, .224, .225])])
    for split, is_unknown in [('train', False), ('train', True),
                              ('validation', False), ('validation', True)]:
        name = f'{split}-{"unknown" if is_unknown else "known"}'
        target = output / f'{name}.npz'
        if target.exists():
            print(f'Existing: {name}', flush=True)
            continue
        source_manifest = (UNKNOWN if is_unknown else ROI) / f'{split}.csv'
        dataset = FeatureDataset(source_manifest, is_unknown,
            allowed if split == 'train' and is_unknown else None)
        dataset.transform = transform
        loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False,
            num_workers=args.workers, pin_memory=device.type == 'cuda')
        features, indices = [], []
        with torch.inference_mode():
            for images, index in loader:
                with torch.autocast(device_type='cuda', enabled=device.type == 'cuda'):
                    embedding = model(images.to(device, non_blocking=True))
                features.append(embedding.float().cpu().numpy())
                indices.extend(index.tolist())
        if indices != list(range(len(dataset))):
            raise ValueError(f'Row order changed: {name}')
        payload = {'features': np.concatenate(features),
            'class_ids': np.array([int(row['class_id']) for row in dataset.rows]),
            'image_ids': np.array([row['image_id'] for row in dataset.rows]),
            'annotation_indices': np.array([int(row['annotation_index'])
                                            for row in dataset.rows])}
        temp = target.with_suffix('.tmp')
        with temp.open('wb') as handle:
            np.savez_compressed(handle, **payload)
        os.replace(temp, target)
        print(f'Saved {name}: {len(dataset)} ROI', flush=True)
    (output / 'manifest.json').write_text(json.dumps({'model': 'official dinov2_vits14',
        'source': str(args.source), 'weights': str(args.weights),
        'weights_sha256': weight_hash,
        'transform': 'Resize 256x256, CenterCrop 224, ImageNet mean/std',
        'unknown_train_ids': sorted(allowed), 'test_used': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
